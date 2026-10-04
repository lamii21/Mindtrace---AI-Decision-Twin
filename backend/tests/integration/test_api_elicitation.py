"""``/v1/elicitation/*`` end to end against real PostgreSQL (M8 planning s19/s26).

Covers: the full fixed-order interview -> ``TwinVersion`` creation; the
``/v1/simulate`` posterior-resolution seam before/after an interview;
historical reproducibility (an old ``Prediction`` stays attached to its
original ``TwinVersion``); finalize idempotency and transaction atomicity;
``TwinVersion`` DB-role immutability and version-allocation concurrency;
posterior serialization/projection parity; latest-answer-wins; consistency
noise; and tenant isolation (ownership + raw RLS).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from mindtrace.api import deps as api_deps
from mindtrace.db.crypto import KeyProvider
from mindtrace.db.repositories import interview_repository, twin_repository
from mindtrace.db.session import get_session, user_scoped_session
from mindtrace.domain.ids import InterviewSessionId, UserId
from mindtrace.domain.traits import PreferencePosterior
from mindtrace.engines.preference.projection import project_effective_weights
from mindtrace.llm.providers.fake import FakeLLMClient
from mindtrace.services import elicitation_service
from tests.integration.conftest import requires_docker
from tests.support.api_helpers import auth_headers, register_and_login
from tests.support.orchestration_fixtures import SCENARIO, TRAIT_MODEL, fully_known_response

pytestmark = requires_docker

_DECISION_BODY = {
    "title": "Take the internship?",
    "category": "career",
    "context": SCENARIO,
    "options": [{"id": "accept", "label": "Accept", "body": "Take the offer"}],
}


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


def _start_session(api_client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = api_client.post("/v1/elicitation/sessions", headers=headers)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _answer_all(
    api_client: TestClient, headers: dict[str, str], session_id: str, *, choice: str = "A"
) -> dict[str, Any]:
    """Answer every fixed-order item; return the final ``ElicitationStep`` body."""
    last: dict[str, Any] | None = None
    for _ in range(50):
        state = api_client.get(f"/v1/elicitation/sessions/{session_id}", headers=headers)
        assert state.status_code == 200, state.text
        next_item = state.json()["next_item"]
        if next_item is None:
            assert last is not None
            return last
        response = api_client.post(
            f"/v1/elicitation/sessions/{session_id}/answers",
            headers=headers,
            json={"item_id": next_item["item_id"], "choice": choice},
        )
        assert response.status_code == 200, response.text
        last = response.json()
    raise AssertionError("fixed order never terminated - possible infinite loop")


def _finalize(api_client: TestClient, headers: dict[str, str], session_id: str) -> Response:
    return api_client.post(f"/v1/elicitation/sessions/{session_id}:finalize", headers=headers)


def _complete_interview(
    api_client: TestClient, headers: dict[str, str], *, choice: str = "A"
) -> dict[str, Any]:
    """Start a session, answer every item, finalize, and return the finalize response body."""
    session = _start_session(api_client, headers)
    _answer_all(api_client, headers, str(session["session_id"]), choice=choice)
    result = _finalize(api_client, headers, str(session["session_id"]))
    assert result.status_code == 200, result.text
    body: dict[str, Any] = result.json()
    return body


class TestHappyPath:
    def test_full_interview_creates_a_twin_version(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)

        result = _complete_interview(api_client, headers)
        assert "twin_id" in result
        assert "twin_version_id" in result
        assert isinstance(result["interview_noise"], float)

        user_id = _decode_user_id(tokens)
        twin_version = twin_repository.get_latest_twin_version(user_id)
        assert twin_version is not None
        assert str(twin_version.id) == result["twin_version_id"]
        assert twin_version.version == 1

    def test_create_session_requires_authentication(self, api_client: TestClient) -> None:
        response = api_client.post("/v1/elicitation/sessions")
        assert response.status_code in (401, 403)

    def test_fresh_session_has_zero_progress_and_a_real_first_item(
        self, api_client: TestClient
    ) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        session = _start_session(api_client, headers)
        assert session["progress"] == {"answered": 0, "target": 24}
        assert session["next_item"]["item_id"] == "p01"


class TestSimulateIntegration:
    def test_twin_version_id_is_null_before_interview_and_populated_after(
        self, api_client: TestClient
    ) -> None:
        _use_llm(api_client, fully_known_response(), fully_known_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)

        before = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()
        assert before["twin_version_id"] is None

        result = _complete_interview(api_client, headers)

        after = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()
        assert after["twin_version_id"] == result["twin_version_id"]


class TestHistoricalReproducibility:
    def test_an_old_prediction_stays_attached_to_its_original_twin_version(
        self, api_client: TestClient
    ) -> None:
        """Prediction A (pre-interview, cold start) and Prediction B (post-interview) must
        each stay attached to the ``twin_version_id`` that was live when they were created -
        a later interview must never retroactively change an already-persisted Prediction."""
        _use_llm(api_client, fully_known_response(), fully_known_response(), fully_known_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)

        prediction_a = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()
        assert prediction_a["twin_version_id"] is None

        first_interview = _complete_interview(api_client, headers)

        prediction_b = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()
        assert prediction_b["twin_version_id"] == first_interview["twin_version_id"]

        # A second interview creates TwinVersion 2 - A and B must not move.
        session = _start_session(api_client, headers)
        _answer_all(api_client, headers, str(session["session_id"]), choice="B")
        second_result = _finalize(api_client, headers, str(session["session_id"]))
        assert second_result.status_code == 200
        second_interview = second_result.json()
        assert second_interview["twin_version_id"] != first_interview["twin_version_id"]

        prediction_a_reread = api_client.get(
            f"/v1/simulations/{prediction_a['simulation_id']}", headers=headers
        ).json()
        prediction_b_reread = api_client.get(
            f"/v1/simulations/{prediction_b['simulation_id']}", headers=headers
        ).json()
        assert prediction_a_reread == prediction_a
        assert prediction_b_reread == prediction_b
        assert prediction_a_reread["twin_version_id"] is None
        assert prediction_b_reread["twin_version_id"] == first_interview["twin_version_id"]

        prediction_c = api_client.post(
            "/v1/simulate", headers=headers, json={"decision_id": decision["id"]}
        ).json()
        assert prediction_c["twin_version_id"] == second_interview["twin_version_id"]


class TestFinalizeIdempotency:
    def test_second_finalize_is_409_with_no_new_version_or_duplicate_evidence(
        self, api_client: TestClient
    ) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        session = _start_session(api_client, headers)
        session_id = str(session["session_id"])
        _answer_all(api_client, headers, session_id)

        first = _finalize(api_client, headers, session_id)
        assert first.status_code == 200

        second = _finalize(api_client, headers, session_id)
        assert second.status_code == 409

        user_id = _decode_user_id(tokens)
        with user_scoped_session(user_id) as db_session:
            version_count: int = db_session.execute(
                text("SELECT count(*) FROM twin_version WHERE user_id = :uid"),
                {"uid": str(user_id)},
            ).scalar_one()
            evidence_count: int = db_session.execute(
                text("SELECT count(*) FROM evidence WHERE user_id = :uid"), {"uid": str(user_id)}
            ).scalar_one()
        assert version_count == 1
        assert evidence_count == 24


class TestFinalizeTransactionAtomicity:
    def test_a_failure_mid_transaction_leaves_no_partial_state(
        self,
        api_client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        key_provider: KeyProvider,
    ) -> None:
        """If the DB write transaction fails after the ``TwinVersion``/``Evidence`` writes
        but before the ``interview_session`` row is marked finalized, NOTHING must survive -
        no ``Twin``, no ``TwinVersion``, no ``Evidence``, and the session stays unfinalized
        (M8 planning s13)."""
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        user_id = _decode_user_id(tokens)
        session = _start_session(api_client, headers)
        session_id = str(session["session_id"])
        _answer_all(api_client, headers, session_id)

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("simulated failure just before commit")

        monkeypatch.setattr(interview_repository, "finalize_session", _boom)

        with pytest.raises(RuntimeError, match="simulated failure"):
            elicitation_service.finalize(
                user_id,
                InterviewSessionId(uuid.UUID(session_id)),
                key_provider=key_provider,
                now=datetime.now(UTC),
            )

        assert twin_repository.get_twin_for_user(user_id) is None
        assert twin_repository.get_latest_twin_version(user_id) is None
        with user_scoped_session(user_id) as db_session:
            evidence_count: int = db_session.execute(
                text("SELECT count(*) FROM evidence WHERE user_id = :uid"), {"uid": str(user_id)}
            ).scalar_one()
            completed_at: datetime | None = db_session.execute(
                text("SELECT completed_at FROM interview_session WHERE id = :sid"),
                {"sid": session_id},
            ).scalar_one()
        assert evidence_count == 0
        assert completed_at is None

        # The session is still usable afterwards - a retried finalize (once the
        # bug is fixed) must succeed normally, proving no corrupted state was left.
        monkeypatch.undo()
        retried = _finalize(api_client, headers, session_id)
        assert retried.status_code == 200


class TestTwinVersionImmutability:
    def test_application_role_cannot_update_twin_version(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        user_id = _decode_user_id(tokens)
        _complete_interview(api_client, headers)

        with (
            pytest.raises(DBAPIError, match="permission denied"),
            user_scoped_session(user_id) as db_session,
        ):
            db_session.execute(
                text("UPDATE twin_version SET version = 999 WHERE user_id = :uid"),
                {"uid": str(user_id)},
            )

    def test_application_role_cannot_delete_twin_version(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        user_id = _decode_user_id(tokens)
        _complete_interview(api_client, headers)

        with (
            pytest.raises(DBAPIError, match="permission denied"),
            user_scoped_session(user_id) as db_session,
        ):
            db_session.execute(
                text("DELETE FROM twin_version WHERE user_id = :uid"), {"uid": str(user_id)}
            )


class TestTwinVersionConcurrency:
    def test_concurrent_finalizes_for_the_same_twin_allocate_distinct_versions(
        self, api_client: TestClient, key_provider: KeyProvider
    ) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        user_id = _decode_user_id(tokens)

        # Twin already exists at version 1.
        _complete_interview(api_client, headers)

        # Two more fully-answered, unfinalized sessions for the SAME user/twin.
        session_2 = _start_session(api_client, headers)
        _answer_all(api_client, headers, str(session_2["session_id"]), choice="B")
        session_3 = _start_session(api_client, headers)
        _answer_all(api_client, headers, str(session_3["session_id"]), choice="A")

        def _finalize_directly(session_id: str) -> int:
            result = elicitation_service.finalize(
                user_id,
                InterviewSessionId(uuid.UUID(session_id)),
                key_provider=key_provider,
                now=datetime.now(UTC),
            )
            return result.twin_version.version

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_2 = pool.submit(_finalize_directly, str(session_2["session_id"]))
            future_3 = pool.submit(_finalize_directly, str(session_3["session_id"]))
            version_2 = future_2.result()
            version_3 = future_3.result()

        assert {version_2, version_3} == {2, 3}

        with user_scoped_session(user_id) as db_session:
            rows: Any = db_session.execute(
                text("SELECT DISTINCT version FROM twin_version WHERE user_id = :uid"),
                {"uid": str(user_id)},
            ).scalars()
            versions: list[int] = [int(v) for v in rows]
        assert sorted(versions) == [1, 2, 3]


class TestPosteriorSerializationAndProjection:
    def test_persisted_posterior_round_trips_and_reprojection_matches_stored_weights(
        self, api_client: TestClient
    ) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        user_id = _decode_user_id(tokens)
        _complete_interview(api_client, headers)

        twin_version = twin_repository.get_latest_twin_version(user_id)
        assert twin_version is not None

        dumped = twin_version.trait_snapshot.model_dump_json()
        reconstructed = PreferencePosterior.model_validate_json(dumped)
        assert reconstructed == twin_version.trait_snapshot

        reprojected = project_effective_weights(twin_version.trait_snapshot, TRAIT_MODEL)
        assert reprojected.weights == twin_version.weights
        assert reprojected.dispositions == twin_version.dispositions
        assert reprojected.projection_version == twin_version.projection_version


class TestPartialSession:
    def test_partial_session_cannot_be_finalized(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        session = _start_session(api_client, headers)
        session_id = str(session["session_id"])

        # Answer only the first item.
        next_item = session["next_item"]
        response = api_client.post(
            f"/v1/elicitation/sessions/{session_id}/answers",
            headers=headers,
            json={"item_id": next_item["item_id"], "choice": "A"},
        )
        assert response.status_code == 200

        result = _finalize(api_client, headers, session_id)
        assert result.status_code == 409

        user_id = _decode_user_id(tokens)
        assert twin_repository.get_twin_for_user(user_id) is None


class TestLatestAnswerWins:
    def test_answering_the_same_item_twice_keeps_only_the_latest(
        self, api_client: TestClient
    ) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        session = _start_session(api_client, headers)
        session_id = str(session["session_id"])
        first_item_id = session["next_item"]["item_id"]

        api_client.post(
            f"/v1/elicitation/sessions/{session_id}/answers",
            headers=headers,
            json={"item_id": first_item_id, "choice": "A"},
        )
        # Re-answer the SAME item with a different choice - progress must not
        # double-count it, and the trait preview must reflect only the latest.
        resubmit = api_client.post(
            f"/v1/elicitation/sessions/{session_id}/answers",
            headers=headers,
            json={"item_id": first_item_id, "choice": "B"},
        )
        assert resubmit.status_code == 200
        body = resubmit.json()
        assert body["progress"]["answered"] == 1
        assert body["next_item"]["item_id"] != first_item_id

        result = _answer_all(api_client, headers, session_id)
        assert result["progress"]["answered"] == result["progress"]["target"]


class TestConsistencyNoiseAtHttpLevel:
    def test_uniformly_answering_a_disagrees_on_every_consistency_pair(
        self, api_client: TestClient
    ) -> None:
        """Documented, smoke-tested fact for this bank: "always A" disagrees on every
        consistency-check pair, so interview_noise == 1.0 (not a vacuous default -
        see ``tests/unit/engines/elicitation/test_finalize.py``)."""
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        result = _complete_interview(api_client, headers, choice="A")
        assert result["interview_noise"] == 1.0


class TestCrossUserOwnership:
    def test_get_session_is_404_for_a_non_owner(self, api_client: TestClient) -> None:
        _email_b, tokens_b = register_and_login(api_client, label="b")
        session = _start_session(api_client, auth_headers(tokens_b))

        _email_a, tokens_a = register_and_login(api_client, label="a")
        response = api_client.get(
            f"/v1/elicitation/sessions/{session['session_id']}", headers=auth_headers(tokens_a)
        )
        assert response.status_code == 404

    def test_submit_answer_is_404_for_a_non_owner(self, api_client: TestClient) -> None:
        _email_b, tokens_b = register_and_login(api_client, label="b")
        session = _start_session(api_client, auth_headers(tokens_b))

        _email_a, tokens_a = register_and_login(api_client, label="a")
        response = api_client.post(
            f"/v1/elicitation/sessions/{session['session_id']}/answers",
            headers=auth_headers(tokens_a),
            json={"item_id": "p01", "choice": "A"},
        )
        assert response.status_code == 404

    def test_finalize_is_404_for_a_non_owner(self, api_client: TestClient) -> None:
        _email_b, tokens_b = register_and_login(api_client, label="b")
        session = _start_session(api_client, auth_headers(tokens_b))
        _answer_all(api_client, auth_headers(tokens_b), str(session["session_id"]))

        _email_a, tokens_a = register_and_login(api_client, label="a")
        response = _finalize(api_client, auth_headers(tokens_a), str(session["session_id"]))
        assert response.status_code == 404


class TestRawDatabaseIsolation:
    def test_raw_unscoped_query_sees_zero_twin_rows(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        _complete_interview(api_client, headers)

        with get_session() as session:
            assert session.execute(text("SELECT id FROM twin")).all() == []
            assert session.execute(text("SELECT id FROM twin_version")).all() == []
            assert session.execute(text("SELECT id FROM interview_session")).all() == []


class TestScenarioAndAnswersNeverLeakPlaintext:
    def test_raw_memory_event_payload_is_ciphertext_not_plaintext_json(
        self, api_client: TestClient
    ) -> None:
        """Interview answers are ``elicitation_answered`` events - stored through the same
        encrypted ``memory_event.payload`` column as every other event (ADR-001/009);
        a raw read must never see the plaintext ``item_id``/``choice`` JSON."""
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        user_id = _decode_user_id(tokens)
        session = _start_session(api_client, headers)
        first_item_id = session["next_item"]["item_id"]
        api_client.post(
            f"/v1/elicitation/sessions/{session['session_id']}/answers",
            headers=headers,
            json={"item_id": first_item_id, "choice": "A"},
        )

        with user_scoped_session(user_id) as db_session:
            raw_payload: bytes = db_session.execute(
                text("SELECT payload FROM memory_event WHERE user_id = :uid"),
                {"uid": str(user_id)},
            ).scalar_one()
        # `payload` is `LargeBinary` - the encrypted envelope (ADR-001/009), never
        # the plaintext JSON `{"item_id": ..., "choice": ...}` a decrypted read
        # would produce.
        assert str(first_item_id).encode() not in bytes(raw_payload)
