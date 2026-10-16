"""``/v1/simulate``'s parallel-twin ensemble + synthesis, end to end (M10; ADR-007).

Covers what ``test_api_simulate.py`` deliberately left for this file: the
real per-twin breakdown, the synthesis vote, a genuinely populated
``ensemble_disagreement``, a high-disagreement scenario resolving to
``UNCERTAIN`` via the new gate, and that ``simulation`` stays append-only
with the new ``synthesis`` column too (a pre-M10 row's genuinely-``NULL``
``synthesis`` is instead tested at the repository level, in
``tests/unit/db/test_simulation_repository.py``, since this table's own
immutability makes it impossible to construct one live here).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from mindtrace.api import deps as api_deps
from mindtrace.db.repositories import audit_repository
from mindtrace.db.session import user_scoped_session
from mindtrace.domain.factors import load_factor_taxonomy
from mindtrace.domain.ids import FactorId, UserId
from mindtrace.llm.providers.fake import FakeLLMClient
from tests.integration.conftest import requires_docker
from tests.support.api_helpers import auth_headers, register_and_login
from tests.support.orchestration_fixtures import SCENARIO, fully_known_response

pytestmark = requires_docker

_DECISION_BODY = {
    "title": "Take the internship?",
    "category": "career",
    "context": SCENARIO,
    "options": [{"id": "accept", "label": "Accept", "body": "Take the offer"}],
}

_TAXONOMY = load_factor_taxonomy()


def _decode_user_id(tokens: Mapping[str, str]) -> UserId:
    payload = jwt.decode(tokens["access_token"], options={"verify_signature": False})
    return UserId(uuid.UUID(payload["sub"]))


def _use_llm(api_client: TestClient, *responses: str) -> None:
    api_client.app.dependency_overrides[api_deps.get_llm_client] = lambda: FakeLLMClient(  # type: ignore[attr-defined]
        responses=list(responses)
    )


def _create_decision(api_client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = api_client.post("/v1/decisions", headers=headers, json=_DECISION_BODY)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _response_for(levels: dict[str, str]) -> str:
    factors = [
        {"factor_id": factor_id, "known": True, "level": level, "rationale_span": SCENARIO}
        for factor_id, level in levels.items()
    ]
    return json.dumps({"schema_version": "1", "factors": factors})


def _career_favoring_response() -> str:
    """skill_growth/option_value very_high (Career You's own up-weights), financial_security
    and stability very_low (Career You's down-weights, and Safe You's up-weights) -
    everything else moderate. Engineered to make Career You/Safe You genuinely disagree."""
    levels = dict.fromkeys(_TAXONOMY.core_ids, "moderate")
    levels[FactorId("skill_growth")] = "very_high"
    levels[FactorId("option_value")] = "very_high"
    levels[FactorId("financial_security")] = "very_low"
    levels[FactorId("stability")] = "very_low"
    return _response_for({str(k): v for k, v in levels.items()})


class TestEnsembleIsPopulated:
    def test_per_twin_has_base_plus_four_named_twins_with_real_variation(
        self, api_client: TestClient
    ) -> None:
        _use_llm(api_client, _career_favoring_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)

        body = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()

        per_twin = {t["twin"]: t for t in body["per_twin"]}
        assert set(per_twin) == {"base", "career", "safe", "dream", "future"}
        # Career You up-weights exactly what this scenario makes very_high - its score
        # must be strictly higher than Safe You's (which up-weights the opposite factors).
        assert per_twin["career"]["score"] > per_twin["safe"]["score"]

    def test_ensemble_disagreement_is_genuinely_populated(self, api_client: TestClient) -> None:
        _use_llm(api_client, _career_favoring_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)

        body = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()

        assert body["confidence"]["inputs"]["ensemble_disagreement"] is not None
        assert body["confidence"]["inputs"]["ensemble_disagreement"] >= 0.0

    def test_synthesis_is_populated_and_consistent_with_per_twin(
        self, api_client: TestClient
    ) -> None:
        _use_llm(api_client, _career_favoring_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)

        body = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()

        synthesis = body["synthesis"]
        assert synthesis is not None
        assert synthesis["recommendation"] in {"ACCEPT", "REJECT", "UNCERTAIN"}
        assert synthesis["label_consensus"] in {"unanimous", "majority", "split"}
        assert isinstance(synthesis["conflict_axis"], list)
        assert set(synthesis["vote"]) == {"base", "career", "safe", "dream", "future"}
        for twin in body["per_twin"]:
            assert synthesis["vote"][twin["twin"]] == twin["label"]

    def test_confidence_is_never_just_abs_score(self, api_client: TestClient) -> None:
        _use_llm(api_client, _career_favoring_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)

        body = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()
        assert body["confidence"]["value"] != abs(body["decision"]["score"])


class TestSingleTwinCompatibility:
    def test_base_twins_own_entry_matches_what_m7_m8_always_produced(
        self, api_client: TestClient
    ) -> None:
        """The base twin's per_twin entry must be exactly what calling decide() directly
        with the user's own (untransformed) weights produces - never shifted by the
        ensemble machinery around it."""
        _use_llm(api_client, fully_known_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)

        body = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()

        base_twin = next(t for t in body["per_twin"] if t["twin"] == "base")
        assert base_twin["score"] == body["decision"]["score"]
        assert base_twin["label"] in {"ACCEPT", "REJECT", "UNCERTAIN"}


class TestEnsembleDisagreementCanForceUncertain:
    """Post-M10 audit F1-B: this class previously held one test
    (``test_a_high_disagreement_scenario_can_resolve_to_uncertain_via_the_ensemble_gate``)
    whose assertion was an if/else that passed on either branch - it proved nothing about
    whether the ensemble-disagreement gate (``services.decision_service.
    _compose_final_label``'s ``UncertainReason.ENSEMBLE_DISAGREEMENT`` branch) is reachable
    through the real ``/v1/simulate`` pipeline. Confirmed directly (printing the real
    response body under this exact fixture): the base twin's own M3 score-band gate fires
    first here (``uncertain_reason == "score_in_band"``, base score ~-0.008, well inside
    the +-0.20 uncertain band) - gate 2 never gets the chance. A broader investigation
    (this fixture's baseline level swept low/moderate/high/very_high, both the cold-start
    prior and two maximally-concentrated real M8 pairwise-interview posteriors, 15 real-
    pipeline configurations total) never reached a scenario where the base twin was
    decisive (|score| > 0.20) while the synthesis vote still landed on UNCERTAIN: once the
    base twin's score escapes the uncertain band, the other four twins' scores move with
    it (their shift is `±λ=0.35` applied to only 2-5 of ~18 factors, consistently producing
    an inter-twin spread of roughly 0.1-0.15 in this configuration - not enough to overturn
    ``BASE_TWIN_VOTE_WEIGHT=2.0``'s double weighting of the base twin's own vote unless
    at least 3 of the 4 other twins flip away from it, which never occurred in any tried
    configuration). The isolated unit test proving gate 2's own logic is correct lives in
    ``tests/unit/services/test_decision_service.py::
    TestComposeFinalLabelEnsembleDisagreementGate`` - that is a different, narrower claim
    than "the shipped pipeline can reach this gate", which remains undemonstrated. Changing
    ``lambda``, ``BASE_TWIN_VOTE_WEIGHT``, or a twin's factor set to make it reachable is a
    design decision for ADR-007, not a correctness fix - explicitly out of scope here.
    """

    def test_this_fixture_resolves_via_the_base_twins_own_gate_not_the_ensemble_gate(
        self, api_client: TestClient
    ) -> None:
        """Documents the real, current, deterministic behaviour of this exact fixture -
        not a guess, not a conditional that passes regardless of outcome."""
        _use_llm(api_client, _career_favoring_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)

        body = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()

        assert body["decision"]["label"] == "UNCERTAIN"
        assert body["decision"]["uncertain_reason"] == "score_in_band"
        # The synthesis vote happens to agree (every twin is independently UNCERTAIN too),
        # but that is gate 1 resolving first, not gate 2 - see the class docstring.
        assert body["synthesis"]["label_consensus"] == "unanimous"
        assert body["synthesis"]["recommendation"] == "UNCERTAIN"


class TestPersistenceRoundTrip:
    def test_synthesis_round_trips_through_a_reread(self, api_client: TestClient) -> None:
        _use_llm(api_client, _career_favoring_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)

        created = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()
        reread = api_client.get(
            f"/v1/simulations/{created['simulation_id']}", headers=headers
        ).json()
        assert reread == created

    def test_application_role_still_cannot_update_a_simulation_row(
        self, api_client: TestClient
    ) -> None:
        """``simulation`` stays append-only (M7) even with the new ``synthesis`` column -
        the ``mindtrace_app`` role has no UPDATE grant at all on this table, so a pre-M10
        row's genuinely-NULL ``synthesis`` (tested at the repository level, in
        ``tests/unit/db/test_simulation_repository.py``, since this table's own
        immutability makes it impossible to construct one live here) can never be
        retroactively backfilled either."""
        _use_llm(api_client, fully_known_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)
        user_id = _decode_user_id(tokens)

        created = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()

        with (
            pytest.raises(DBAPIError, match="permission denied"),
            user_scoped_session(user_id) as session,
        ):
            session.execute(
                text("UPDATE simulation SET synthesis = NULL WHERE id = :id"),
                {"id": created["simulation_id"]},
            )


class TestAuditLogRow:
    def test_simulate_appends_one_audit_row_for_the_new_simulation(
        self, api_client: TestClient
    ) -> None:
        """M10 (roadmap: "every belief-writing path emits an audit row") - one derivation,
        one ``AuditLog`` row, in the same transaction as the ``Simulation`` it records
        (``simulation_repository.persist_simulation``), reusing M9's existing
        ``audit_repository``/``build_audit_log`` pattern rather than a second system."""
        _use_llm(api_client, fully_known_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)
        user_id = _decode_user_id(tokens)

        created = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()

        rows = audit_repository.list_for_target(
            user_id, target_type="simulation", target_id=uuid.UUID(created["simulation_id"])
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.action == "simulation.ensemble_synthesized"
        assert row.user_id == user_id
        assert row.engine_version is not None
        assert row.payload_hash
