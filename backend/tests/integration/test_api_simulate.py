"""``/v1/simulate`` + ``/v1/simulations/{id}`` end to end against real PostgreSQL (M7 planning s23).

``api_client`` is function-scoped (a fresh ``TestClient``/``FastAPI`` app per
test), so overriding ``get_llm_client`` on ``api_client.app`` here never
leaks into another test.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import text

from mindtrace.api import deps as api_deps
from mindtrace.api.idempotency import fingerprint
from mindtrace.db.crypto import KeyProvider
from mindtrace.db.repositories.evidence_repository import PostgresEvidenceStore
from mindtrace.db.session import get_session, user_scoped_session
from mindtrace.domain.enums import EvidenceSourceKind
from mindtrace.domain.ids import DecisionId, UserId
from mindtrace.llm.config import ExtractionConfig
from mindtrace.llm.providers.fake import FakeLLMClient
from mindtrace.orchestration import SimulationConfig
from mindtrace.orchestration import simulate as orchestrate_simulate
from mindtrace.services import decision_service, idempotency_service
from tests.integration.conftest import requires_docker
from tests.support.api_helpers import auth_headers, register_and_login
from tests.support.orchestration_fixtures import (
    SCENARIO,
    TAXONOMY,
    TRAIT_MODEL,
    cold_start_posterior,
    fully_known_response,
    sparse_response,
)

pytestmark = requires_docker

_DECISION_BODY = {
    "title": "Take the internship?",
    "category": "career",
    "context": SCENARIO,
    "options": [{"id": "accept", "label": "Accept", "body": "Take the offer"}],
}

# Matches `services.decision_service._DEFAULT_EXTRACTION_CONFIG` exactly, so
# the direct-orchestrator-parity tests below compute against the identical
# config the HTTP path actually used.
_EXTRACTION_CONFIG = ExtractionConfig(provider="unavailable", model="none")


def _use_llm(api_client: TestClient, *responses: str) -> None:
    api_client.app.dependency_overrides[api_deps.get_llm_client] = lambda: FakeLLMClient(  # type: ignore[attr-defined]
        responses=list(responses)
    )


def _clean_accept_response() -> str:
    """9 "high" known factors (of the first 14 core factors): MCDA says ACCEPT and confidence
    (~0.4) clears ``C_MIN``=0.35 - the "nothing gated" branch of ``_compose_final_label``."""
    known_ids = list(TAXONOMY.core_ids)[:14]
    levels = ["high"] * 9 + ["moderate"] * 5
    factors = [
        {"factor_id": str(fid), "known": True, "level": level, "rationale_span": SCENARIO}
        for fid, level in zip(known_ids, levels, strict=True)
    ]
    return json.dumps({"schema_version": "1", "factors": factors})


def _gated_low_confidence_response() -> str:
    """7 "high" + 7 "moderate" (of the first 14 core factors): MCDA alone says ACCEPT (no
    ``uncertain_reason``) with confidence ~0.257 < ``C_MIN``=0.35 - found empirically (M7
    planning). Exercises the confidence-gate composition path where the persisted
    ``Prediction.predicted_decision`` is overridden to ``UNCERTAIN``/``low_model_confidence``
    even though M3's own raw ``decision.label`` stays ``ACCEPT``.
    """
    known_ids = list(TAXONOMY.core_ids)[:14]
    levels = ["high"] * 7 + ["moderate"] * 7
    factors = [
        {"factor_id": str(fid), "known": True, "level": level, "rationale_span": SCENARIO}
        for fid, level in zip(known_ids, levels, strict=True)
    ]
    return json.dumps({"schema_version": "1", "factors": factors})


def _create_decision(api_client: TestClient, headers: dict[str, str]) -> dict[str, object]:
    response = api_client.post("/v1/decisions", headers=headers, json=_DECISION_BODY)
    assert response.status_code == 201, response.text
    result: dict[str, object] = response.json()
    return result


class TestHappyPath:
    def test_simulate_persists_and_transitions_decision(self, api_client: TestClient) -> None:
        _use_llm(api_client, fully_known_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)

        response = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["decision_id"] == decision["id"]
        assert body["twin_version_id"] is None
        assert body["synthesis"] is None
        assert body["debate"] is None
        assert body["elicitation_hint"] is None
        assert len(body["per_twin"]) == 1
        assert body["per_twin"][0]["twin"] == "base"

        decision_after = api_client.get(f"/v1/decisions/{decision['id']}", headers=headers).json()
        assert decision_after["status"] == "simulated"

        get_resp = api_client.get(f"/v1/simulations/{body['simulation_id']}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json() == body

        listing = api_client.get(
            f"/v1/decisions/{decision['id']}/simulations", headers=headers
        ).json()
        assert len(listing["items"]) == 1
        assert listing["items"][0]["simulation_id"] == body["simulation_id"]

    def test_create_requires_authentication(self, api_client: TestClient) -> None:
        response = api_client.post("/v1/simulate", json={"decision_id": str(uuid.uuid4())})
        assert response.status_code in (401, 403)

    def test_simulate_unknown_decision_is_404(self, api_client: TestClient) -> None:
        _use_llm(api_client, fully_known_response())
        _email, tokens = register_and_login(api_client)
        response = api_client.post(
            "/v1/simulate",
            headers=auth_headers(tokens),
            json={"decision_id": str(uuid.uuid4())},
        )
        assert response.status_code == 404


class TestDirectOrchestratorParity:
    """The persisted/returned result must match a direct ``orchestration.simulate()`` call
    exactly - no hidden math in the service or the router (M7 planning s23 test B/K)."""

    def test_score_confidence_contributions_match_direct_orchestrator_call(
        self, api_client: TestClient
    ) -> None:
        response_text = fully_known_response()
        _use_llm(api_client, response_text)
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)

        response = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        )
        assert response.status_code == 200
        body = response.json()

        direct = orchestrate_simulate(
            SCENARIO,
            TAXONOMY,
            TRAIT_MODEL,
            cold_start_posterior(),
            FakeLLMClient(responses=[response_text]),
            config=SimulationConfig(extraction_config=_EXTRACTION_CONFIG),
        )

        assert body["decision"]["score"] == direct.decision.score
        assert body["decision"]["margin"] == direct.decision.margin
        assert body["decision"]["coverage"] == direct.decision.coverage
        assert body["confidence"]["value"] == direct.confidence.value
        assert body["confidence"]["raw"] == direct.confidence.raw
        assert len(body["contributions"]) == len(direct.decision.contributions)
        for out, direct_c in zip(body["contributions"], direct.decision.contributions, strict=True):
            assert out["factor_id"] == direct_c.factor_id
            assert out["raw_contribution"] == direct_c.raw_contribution
            assert out["contribution_pct"] == direct_c.contribution_pct


class TestScoreConfidenceSeparation:
    def test_score_and_confidence_are_never_the_same_value_or_derived_from_each_other(
        self, api_client: TestClient
    ) -> None:
        _use_llm(api_client, fully_known_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)

        body = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()
        score = body["decision"]["score"]
        confidence = body["confidence"]["value"]
        # The full-coverage, all-"moderate" fixture nets to a near-zero score
        # but a real, independently-computed confidence - not `abs(score)`.
        assert confidence != abs(score)

    def test_low_coverage_gives_a_strong_signal_but_near_zero_confidence(
        self, api_client: TestClient
    ) -> None:
        """S can be computed even when C is near-zero - they survive independently."""
        _use_llm(api_client, sparse_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)

        body = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()
        assert body["decision"]["label"] == "UNCERTAIN"
        assert body["decision"]["uncertain_reason"] == "insufficient_coverage"
        # Both persisted, both independently inspectable, neither fabricated.
        assert isinstance(body["decision"]["score"], float)
        assert isinstance(body["confidence"]["value"], float)


class TestConfidenceGateComposition:
    def test_adequate_confidence_leaves_an_mcda_accept_label_untouched(
        self, api_client: TestClient
    ) -> None:
        """The "nothing gated" branch: M3 says ACCEPT, confidence clears C_MIN, both survive."""
        _use_llm(api_client, _clean_accept_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)

        body = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()
        assert body["decision"]["label"] == "ACCEPT"
        assert body["decision"]["uncertain_reason"] is None
        assert body["confidence"]["value"] >= 0.35

    def test_low_confidence_overrides_an_mcda_accept_label_to_uncertain(
        self, api_client: TestClient
    ) -> None:
        """M3 alone says ACCEPT; the service-composed, persisted label must be UNCERTAIN.

        Confirms the gate fires in the product-level composition
        (``decision_service._compose_final_label``), never inside
        ``engines.mcda``/``engines.confidence`` themselves.
        """
        response_text = _gated_low_confidence_response()
        _use_llm(api_client, response_text)
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)

        body = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()

        # The persisted, product-level label is gated...
        assert body["decision"]["label"] == "UNCERTAIN"
        assert body["decision"]["uncertain_reason"] == "low_model_confidence"
        # ...but M3's raw score/margin/coverage are never adjusted - the
        # per-twin raw MCDA label (ACCEPT) survives untouched alongside it.
        assert body["per_twin"][0]["label"] == "ACCEPT"
        assert body["confidence"]["value"] < 0.35


class TestExtractionFailure:
    def test_provider_unavailable_yields_uncertain_never_a_500(
        self, api_client: TestClient
    ) -> None:
        """No override: the real default DI (``UnavailableLLMClient``) always raises the
        typed ``ProviderUnavailableError`` - a provider failure is a valid
        ``ExtractionOutcome``, not an infrastructure error."""
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)

        response = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["decision"]["label"] == "UNCERTAIN"
        assert body["decision"]["uncertain_reason"] == "insufficient_coverage"
        assert body["contributions"] == []


class TestOwnership:
    def test_user_a_cannot_get_user_bs_simulation(self, api_client: TestClient) -> None:
        _use_llm(api_client, fully_known_response())
        _email_b, tokens_b = register_and_login(api_client, label="b")
        headers_b = auth_headers(tokens_b)
        decision = _create_decision(api_client, headers_b)
        sim = api_client.post(
            "/v1/simulate", headers=headers_b, json={"decision_id": decision["id"]}
        ).json()

        _email_a, tokens_a = register_and_login(api_client, label="a")
        response = api_client.get(
            f"/v1/simulations/{sim['simulation_id']}", headers=auth_headers(tokens_a)
        )
        assert response.status_code == 404

    def test_user_a_cannot_list_user_bs_decision_simulations(self, api_client: TestClient) -> None:
        _use_llm(api_client, fully_known_response())
        _email_b, tokens_b = register_and_login(api_client, label="b")
        headers_b = auth_headers(tokens_b)
        decision = _create_decision(api_client, headers_b)
        api_client.post("/v1/simulate", headers=headers_b, json={"decision_id": decision["id"]})

        _email_a, tokens_a = register_and_login(api_client, label="a")
        response = api_client.get(
            f"/v1/decisions/{decision['id']}/simulations", headers=auth_headers(tokens_a)
        )
        assert response.status_code == 404

    def test_user_a_cannot_simulate_user_bs_decision(self, api_client: TestClient) -> None:
        _use_llm(api_client, fully_known_response())
        _email_b, tokens_b = register_and_login(api_client, label="b")
        decision = _create_decision(api_client, auth_headers(tokens_b))

        _email_a, tokens_a = register_and_login(api_client, label="a")
        response = api_client.post(
            "/v1/simulate", headers=auth_headers(tokens_a), json={"decision_id": decision["id"]}
        )
        assert response.status_code == 404


class TestRawDatabaseIsolation:
    def test_raw_unscoped_query_sees_zero_simulation_prediction_evidence_rows(
        self, api_client: TestClient
    ) -> None:
        _use_llm(api_client, fully_known_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)
        api_client.post("/v1/simulate", headers=headers, json={"decision_id": decision["id"]})

        with get_session() as session:
            assert session.execute(text("SELECT id FROM simulation")).all() == []
            assert session.execute(text("SELECT id FROM prediction")).all() == []
            assert session.execute(text("SELECT id FROM evidence")).all() == []


class TestScenarioTextNeverPersistedInSimulation:
    def test_raw_simulation_row_never_contains_the_scenario_text(
        self, api_client: TestClient
    ) -> None:
        """``extraction`` is plaintext JSONB (ADR-009: nothing sensitive) - but it must still
        never contain the literal scenario text, since ``rationale_spans`` are excluded by
        construction (``domain/simulation.py`` module docstring, M7 planning s7)."""
        _use_llm(api_client, fully_known_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)
        sim = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()

        with user_scoped_session(_decode_user_id(tokens)) as session:
            raw_extraction: str = session.execute(
                text("SELECT extraction::text FROM simulation WHERE id = :id"),
                {"id": sim["simulation_id"]},
            ).scalar_one()
        assert SCENARIO not in raw_extraction


class TestSimulateConvenienceWrapper:
    def test_decision_service_simulate_validates_then_runs_in_one_call(
        self, api_client: TestClient
    ) -> None:
        """``decision_service.simulate()`` - the combined validate+run entry point tests and
        non-idempotent callers use, as opposed to the router's split validate/claim/run."""
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)
        user_id = _decode_user_id(tokens)
        key_provider: KeyProvider = api_deps.get_key_provider()

        simulation, prediction = decision_service.simulate(
            user_id=user_id,
            decision_id=DecisionId(uuid.UUID(str(decision["id"]))),
            llm_client=FakeLLMClient(responses=[fully_known_response()]),
            key_provider=key_provider,
            now=datetime.now(UTC),
        )
        assert simulation.decision_id == prediction.decision_id
        assert prediction.simulation_id == simulation.id


class TestEvidenceRepository:
    def test_for_source_finds_the_edge_by_decision_id(self, api_client: TestClient) -> None:
        """The reverse lookup (``EvidenceStore.for_source``) M9's deletion cascade will use."""
        _use_llm(api_client, fully_known_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)
        api_client.post("/v1/simulate", headers=headers, json={"decision_id": decision["id"]})

        user_id = _decode_user_id(tokens)
        with user_scoped_session(user_id) as session:
            edges = PostgresEvidenceStore(session, user_id=user_id).for_source(
                EvidenceSourceKind.DECISION, uuid.UUID(str(decision["id"]))
            )
        assert len(edges) == 1
        assert edges[0].source_id == uuid.UUID(str(decision["id"]))


class TestDecisionLifecycle:
    def test_archived_decision_cannot_be_simulated(self, api_client: TestClient) -> None:
        _use_llm(api_client, fully_known_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)
        api_client.patch(
            f"/v1/decisions/{decision['id']}", headers=headers, json={"status": "archived"}
        )

        response = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        )
        assert response.status_code == 409

    def test_client_patch_cannot_fabricate_simulated_status(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)
        response = api_client.patch(
            f"/v1/decisions/{decision['id']}", headers=headers, json={"status": "simulated"}
        )
        assert response.status_code == 409

    def test_resimulating_creates_a_new_simulation_and_does_not_revert_committed_status(
        self, api_client: TestClient
    ) -> None:
        _use_llm(api_client, fully_known_response(), fully_known_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)

        first = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()

        api_client.patch(
            f"/v1/decisions/{decision['id']}",
            headers=headers,
            json={"chosen_option": "accept", "status": "committed"},
        )
        committed = api_client.get(f"/v1/decisions/{decision['id']}", headers=headers).json()
        assert committed["status"] == "committed"

        second = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()
        assert second["simulation_id"] != first["simulation_id"]

        # Re-simulating a committed decision must not revert its status.
        still_committed = api_client.get(f"/v1/decisions/{decision['id']}", headers=headers).json()
        assert still_committed["status"] == "committed"

        listing = api_client.get(
            f"/v1/decisions/{decision['id']}/simulations", headers=headers
        ).json()
        assert len(listing["items"]) == 2


class TestIdempotency:
    def test_same_key_and_body_returns_the_same_simulation(self, api_client: TestClient) -> None:
        _use_llm(api_client, fully_known_response(), fully_known_response())
        _email, tokens = register_and_login(api_client)
        headers = {**auth_headers(tokens), "Idempotency-Key": "fixed-sim-key-1"}
        decision = _create_decision(api_client, auth_headers(tokens))
        body = {"decision_id": decision["id"]}

        first = api_client.post("/v1/simulate", headers=headers, json=body)
        second = api_client.post("/v1/simulate", headers=headers, json=body)
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["simulation_id"] == second.json()["simulation_id"]

        listing = api_client.get(
            f"/v1/decisions/{decision['id']}/simulations", headers=auth_headers(tokens)
        ).json()
        assert len(listing["items"]) == 1

    def test_same_key_different_decision_is_a_409_conflict(self, api_client: TestClient) -> None:
        _use_llm(api_client, fully_known_response(), fully_known_response())
        _email, tokens = register_and_login(api_client)
        headers = {**auth_headers(tokens), "Idempotency-Key": "fixed-sim-key-2"}
        decision_a = _create_decision(api_client, auth_headers(tokens))
        decision_b = _create_decision(api_client, auth_headers(tokens))

        first = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision_a["id"]}
        )
        second = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision_b["id"]}
        )
        assert first.status_code == 200
        assert second.status_code == 409

    def test_claimed_but_unfinished_key_reports_in_progress_not_a_duplicate_run(
        self, api_client: TestClient
    ) -> None:
        """The reserve-before-compute race window: a claim exists, but no Simulation row yet.

        Simulates the loser's-eye view of a genuinely concurrent request by
        pre-claiming the exact key/fingerprint the router would compute for
        this body, then hitting the endpoint - it must see the winner's
        claim (unfinished) and report 409, never silently run its own LLM
        call (M7 planning s20).
        """
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)
        body = {"decision_id": decision["id"]}
        user_id = _decode_user_id(tokens)

        idempotency_service.claim_or_replay(
            user_id=user_id,
            route="POST /v1/simulate",
            idempotency_key="in-flight-key",
            request_fingerprint=fingerprint(body),
            resource_id=uuid.uuid4(),  # a simulation id that will never exist
            response_status=200,
            now=datetime.now(UTC),
        )

        response = api_client.post(
            "/v1/simulate",
            headers={**headers, "Idempotency-Key": "in-flight-key"},
            json=body,
        )
        assert response.status_code == 409


def _decode_user_id(tokens: dict[str, str]) -> UserId:
    payload = jwt.decode(tokens["access_token"], options={"verify_signature": False})
    return UserId(uuid.UUID(payload["sub"]))
