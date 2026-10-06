"""``/v1/evidence``, ``/v1/beliefs/*:dispute``, and the enriched ``DeletionPlan`` (M9).

Covers: evidence chain reads for both real producers (``decision_factor``
from ``/v1/simulate``, ``preference`` from the M8 interview); disputes
(happy path -> new ``TwinVersion`` + ``/v1/simulate`` picking it up,
unsupported ``belief_type``, invalid ``item_id``, stale ``belief_id``,
cross-user non-leakage); the real ``PostgresEvidenceStore`` wiring into
``DeletionPlan`` (a synthetic memory-sourced ``Evidence`` edge, since no
current producer writes one); ``AuditLog`` writes + DB-role immutability;
raw RLS isolation; and that a dispute's ``reason`` never appears as
plaintext anywhere outside the encrypted event payload.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from mindtrace.api import deps as api_deps
from mindtrace.db.repositories import audit_repository, twin_repository
from mindtrace.db.repositories.evidence_repository import PostgresEvidenceStore
from mindtrace.db.session import get_session, user_scoped_session
from mindtrace.domain.enums import BeliefType, EvidenceSourceKind, Polarity
from mindtrace.domain.evidence import Evidence
from mindtrace.domain.ids import EvidenceId, UserId
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


def _simulate(api_client: TestClient, headers: dict[str, str], decision_id: str) -> dict[str, Any]:
    response = api_client.post("/v1/simulate", headers=headers, json={"decision_id": decision_id})
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def _answer_all(
    api_client: TestClient, headers: dict[str, str], session_id: str, *, choice: str = "A"
) -> None:
    for _ in range(50):
        state = api_client.get(f"/v1/elicitation/sessions/{session_id}", headers=headers)
        next_item = state.json()["next_item"]
        if next_item is None:
            return
        response = api_client.post(
            f"/v1/elicitation/sessions/{session_id}/answers",
            headers=headers,
            json={"item_id": next_item["item_id"], "choice": choice},
        )
        assert response.status_code == 200, response.text
    raise AssertionError("fixed order never terminated")


def _complete_interview(
    api_client: TestClient, headers: dict[str, str], *, choice: str = "A"
) -> dict[str, Any]:
    session = api_client.post("/v1/elicitation/sessions", headers=headers)
    assert session.status_code == 201, session.text
    session_id = str(session.json()["session_id"])
    _answer_all(api_client, headers, session_id, choice=choice)
    result = api_client.post(f"/v1/elicitation/sessions/{session_id}:finalize", headers=headers)
    assert result.status_code == 200, result.text
    body: dict[str, Any] = result.json()
    return body


class TestEvidenceChainForDecisionFactor:
    def test_returns_the_chain_after_a_simulate(self, api_client: TestClient) -> None:
        _use_llm(api_client, fully_known_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)
        simulation = _simulate(api_client, headers, decision["id"])

        response = api_client.get(
            f"/v1/evidence/decision_factor/{simulation['simulation_id']}", headers=headers
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["belief"]["type"] == "decision_factor"
        assert body["belief"]["id"] == simulation["simulation_id"]
        assert body["belief"]["source"] == "inferred"
        assert len(body["edges"]) == 1
        edge = body["edges"][0]
        assert edge["source_kind"] == "decision"
        assert edge["source_id"] == decision["id"]
        assert "decision" in edge["source_excerpt"]

    def test_404_for_an_unknown_belief(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        response = api_client.get(
            f"/v1/evidence/decision_factor/{uuid.uuid4()}", headers=auth_headers(tokens)
        )
        assert response.status_code == 404

    def test_404_for_another_users_belief(self, api_client: TestClient) -> None:
        _use_llm(api_client, fully_known_response())
        _email_b, tokens_b = register_and_login(api_client, label="b")
        headers_b = auth_headers(tokens_b)
        decision = _create_decision(api_client, headers_b)
        simulation = _simulate(api_client, headers_b, decision["id"])

        _email_a, tokens_a = register_and_login(api_client, label="a")
        response = api_client.get(
            f"/v1/evidence/decision_factor/{simulation['simulation_id']}",
            headers=auth_headers(tokens_a),
        )
        assert response.status_code == 404


class TestEvidenceChainForPreference:
    def test_returns_the_chain_after_an_interview(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        interview = _complete_interview(api_client, headers)

        response = api_client.get(
            f"/v1/evidence/preference/{interview['twin_version_id']}", headers=headers
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["belief"]["type"] == "preference"
        assert body["belief"]["source"] == "inferred"
        assert len(body["edges"]) == 24
        assert all(edge["source_kind"] == "elicitation_answer" for edge in body["edges"])
        assert all(edge["source_excerpt"] for edge in body["edges"])

    def test_includes_a_decrypted_excerpt_for_a_memory_sourced_edge(
        self, api_client: TestClient
    ) -> None:
        """No current producer writes ``Evidence(source_kind=memory)`` - this injects one
        directly (as a future producer would) to prove the excerpt path is real, mirroring
        ``TestDeletionPlanEnrichment``'s own synthetic-edge technique (M9 planning)."""
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        user_id = _decode_user_id(tokens)
        interview = _complete_interview(api_client, headers)

        memory_response = api_client.post(
            "/v1/memories",
            headers=headers,
            json={"kind": "note", "text": "I deeply value my independence.", "source": "declared"},
        )
        assert memory_response.status_code == 202
        memory_id = memory_response.json()["memory_id"]

        with user_scoped_session(user_id) as session:
            PostgresEvidenceStore(session, user_id=user_id).record(
                Evidence(
                    id=EvidenceId(uuid.uuid4()),
                    user_id=user_id,
                    belief_type=BeliefType.PREFERENCE,
                    belief_id=uuid.UUID(interview["twin_version_id"]),
                    source_kind=EvidenceSourceKind.MEMORY,
                    source_id=uuid.UUID(memory_id),
                    weight=1.0,
                    polarity=Polarity.SUPPORT,
                    engine_version="synthetic-test-fixture",
                    created_at=datetime.now(UTC),
                )
            )

        response = api_client.get(
            f"/v1/evidence/preference/{interview['twin_version_id']}", headers=headers
        )
        assert response.status_code == 200, response.text
        edges = response.json()["edges"]
        memory_edges = [e for e in edges if e["source_kind"] == "memory"]
        assert len(memory_edges) == 1
        assert memory_edges[0]["source_excerpt"] == "I deeply value my independence."


class TestDispute:
    def test_happy_path_creates_a_new_twin_version_simulate_uses_it(
        self, api_client: TestClient
    ) -> None:
        _use_llm(api_client, fully_known_response(), fully_known_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        interview = _complete_interview(api_client, headers)
        decision = _create_decision(api_client, headers)
        before = _simulate(api_client, headers, decision["id"])
        assert before["twin_version_id"] == interview["twin_version_id"]

        response = api_client.post(
            f"/v1/beliefs/preference/{interview['twin_version_id']}:dispute",
            headers=headers,
            json={
                "reason": "I actually care much more about autonomy.",
                "item_id": "p01",
                "choice": "B",
            },
        )
        assert response.status_code == 202, response.text
        body = response.json()
        assert "event_id" in body
        assert "job_id" in body

        user_id = _decode_user_id(tokens)
        new_version = twin_repository.get_latest_twin_version(user_id)
        assert new_version is not None
        assert str(new_version.id) != interview["twin_version_id"]
        assert new_version.version == 2

        after = _simulate(api_client, headers, decision["id"])
        assert after["twin_version_id"] == str(new_version.id)

    def test_unsupported_belief_type_is_422(self, api_client: TestClient) -> None:
        _use_llm(api_client, fully_known_response())
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        decision = _create_decision(api_client, headers)
        simulation = _simulate(api_client, headers, decision["id"])

        response = api_client.post(
            f"/v1/beliefs/decision_factor/{simulation['simulation_id']}:dispute",
            headers=headers,
            json={"reason": "disagree", "item_id": "p01", "choice": "A"},
        )
        assert response.status_code == 422

    def test_invalid_item_id_is_422(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        interview = _complete_interview(api_client, headers)

        response = api_client.post(
            f"/v1/beliefs/preference/{interview['twin_version_id']}:dispute",
            headers=headers,
            json={"reason": "disagree", "item_id": "not-a-real-item", "choice": "A"},
        )
        assert response.status_code == 422

    def test_stale_belief_id_is_409(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        first_interview = _complete_interview(api_client, headers)

        # A second full interview creates TwinVersion 2 - version 1 is now stale.
        _complete_interview(api_client, headers, choice="B")

        response = api_client.post(
            f"/v1/beliefs/preference/{first_interview['twin_version_id']}:dispute",
            headers=headers,
            json={"reason": "disagree", "item_id": "p01", "choice": "A"},
        )
        assert response.status_code == 409

    def test_disputing_another_users_belief_is_409_and_does_not_affect_it(
        self, api_client: TestClient
    ) -> None:
        _email_b, tokens_b = register_and_login(api_client, label="b")
        headers_b = auth_headers(tokens_b)
        interview_b = _complete_interview(api_client, headers_b)

        _email_a, tokens_a = register_and_login(api_client, label="a")
        headers_a = auth_headers(tokens_a)
        response = api_client.post(
            f"/v1/beliefs/preference/{interview_b['twin_version_id']}:dispute",
            headers=headers_a,
            json={"reason": "not my belief", "item_id": "p01", "choice": "A"},
        )
        assert response.status_code == 409

        user_b_id = _decode_user_id(tokens_b)
        version_b = twin_repository.get_latest_twin_version(user_b_id)
        assert version_b is not None
        assert str(version_b.id) == interview_b["twin_version_id"]
        assert version_b.version == 1

    def test_writes_an_audit_log_row(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        interview = _complete_interview(api_client, headers)
        user_id = _decode_user_id(tokens)

        api_client.post(
            f"/v1/beliefs/preference/{interview['twin_version_id']}:dispute",
            headers=headers,
            json={"reason": "disagree", "item_id": "p01", "choice": "B"},
        )

        new_version = twin_repository.get_latest_twin_version(user_id)
        assert new_version is not None
        rows = audit_repository.list_for_target(
            user_id, target_type="twin_version", target_id=uuid.UUID(str(new_version.id))
        )
        assert len(rows) == 1
        assert rows[0].action == "belief.disputed"
        assert len(rows[0].payload_hash) == 64

    def test_never_mutates_the_disputed_twin_version(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        interview = _complete_interview(api_client, headers)
        user_id = _decode_user_id(tokens)
        before_dispute = twin_repository.get_latest_twin_version(user_id)
        assert before_dispute is not None
        original = twin_repository.get_twin_version(user_id, before_dispute.id)
        assert original is not None

        api_client.post(
            f"/v1/beliefs/preference/{interview['twin_version_id']}:dispute",
            headers=headers,
            json={"reason": "disagree", "item_id": "p01", "choice": "B"},
        )

        reread = twin_repository.get_twin_version(user_id, original.id)
        assert reread == original


class TestDeletionPlanEnrichment:
    def test_a_real_memory_sourced_evidence_edge_is_reflected_in_the_plan(
        self, api_client: TestClient
    ) -> None:
        """No current producer writes ``Evidence(source_kind=memory)`` - this injects one
        directly (as a future producer would) to prove the DeletionPlan wiring is real,
        not just structurally present (M9 planning)."""
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        user_id = _decode_user_id(tokens)
        interview = _complete_interview(api_client, headers)

        memory_response = api_client.post(
            "/v1/memories",
            headers=headers,
            json={"kind": "note", "text": "I love hiking.", "source": "declared"},
        )
        assert memory_response.status_code == 202
        memory_id = memory_response.json()["memory_id"]

        with user_scoped_session(user_id) as session:
            PostgresEvidenceStore(session, user_id=user_id).record(
                Evidence(
                    id=EvidenceId(uuid.uuid4()),
                    user_id=user_id,
                    belief_type=BeliefType.PREFERENCE,
                    belief_id=uuid.UUID(interview["twin_version_id"]),
                    source_kind=EvidenceSourceKind.MEMORY,
                    source_id=uuid.UUID(memory_id),
                    weight=1.0,
                    polarity=Polarity.SUPPORT,
                    engine_version="synthetic-test-fixture",
                    created_at=datetime.now(UTC),
                )
            )

        response = api_client.delete(
            f"/v1/memories/{memory_id}", headers=headers, params={"dry_run": "true"}
        )
        assert response.status_code == 200, response.text
        plan = response.json()
        assert plan["target_memory_ids"] == [memory_id]
        assert len(plan["affected_beliefs"]) == 1
        belief = plan["affected_beliefs"][0]
        assert belief["belief_type"] == "preference"
        assert belief["belief_id"] == interview["twin_version_id"]
        assert belief["change"] == "recompute"
        assert plan["twin_version_will_bump"] is True
        assert plan["reversible"] is False

    def test_apply_delete_writes_an_audit_log_row(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        user_id = _decode_user_id(tokens)

        memory_response = api_client.post(
            "/v1/memories",
            headers=headers,
            json={"kind": "note", "text": "disposable memory", "source": "declared"},
        )
        memory_id = memory_response.json()["memory_id"]

        response = api_client.delete(
            f"/v1/memories/{memory_id}", headers=headers, params={"dry_run": "false"}
        )
        assert response.status_code == 202

        rows = audit_repository.list_for_target(
            user_id, target_type="memory", target_id=uuid.UUID(memory_id)
        )
        assert len(rows) == 1
        assert rows[0].action == "memory.deleted"


class TestAuditLogImmutability:
    def test_application_role_cannot_update_audit_log(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        user_id = _decode_user_id(tokens)
        interview = _complete_interview(api_client, headers)
        api_client.post(
            f"/v1/beliefs/preference/{interview['twin_version_id']}:dispute",
            headers=headers,
            json={"reason": "disagree", "item_id": "p01", "choice": "B"},
        )

        with (
            pytest.raises(DBAPIError, match="permission denied"),
            user_scoped_session(user_id) as session,
        ):
            session.execute(
                text("UPDATE audit_log SET action = 'tampered' WHERE user_id = :uid"),
                {"uid": str(user_id)},
            )

    def test_application_role_cannot_delete_audit_log(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        user_id = _decode_user_id(tokens)
        interview = _complete_interview(api_client, headers)
        api_client.post(
            f"/v1/beliefs/preference/{interview['twin_version_id']}:dispute",
            headers=headers,
            json={"reason": "disagree", "item_id": "p01", "choice": "B"},
        )

        with (
            pytest.raises(DBAPIError, match="permission denied"),
            user_scoped_session(user_id) as session,
        ):
            session.execute(
                text("DELETE FROM audit_log WHERE user_id = :uid"), {"uid": str(user_id)}
            )


class TestRawDatabaseIsolation:
    def test_raw_unscoped_query_sees_zero_audit_log_rows(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        interview = _complete_interview(api_client, headers)
        api_client.post(
            f"/v1/beliefs/preference/{interview['twin_version_id']}:dispute",
            headers=headers,
            json={"reason": "disagree", "item_id": "p01", "choice": "B"},
        )

        with get_session() as session:
            assert session.execute(text("SELECT id FROM audit_log")).all() == []


class TestEncryptionAndPrivacy:
    def test_dispute_reason_never_appears_in_plaintext_anywhere(
        self, api_client: TestClient
    ) -> None:
        secret_reason = "MY-SECRET-DISPUTE-REASON-12345"
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        user_id = _decode_user_id(tokens)
        interview = _complete_interview(api_client, headers)

        api_client.post(
            f"/v1/beliefs/preference/{interview['twin_version_id']}:dispute",
            headers=headers,
            json={"reason": secret_reason, "item_id": "p01", "choice": "B"},
        )

        with user_scoped_session(user_id) as session:
            payload_rows: Any = session.execute(
                text("SELECT payload FROM memory_event WHERE user_id = :uid"),
                {"uid": str(user_id)},
            ).scalars()
            raw_payloads: list[bytes] = list(payload_rows)
            hash_rows: Any = session.execute(
                text("SELECT payload_hash FROM audit_log WHERE user_id = :uid"),
                {"uid": str(user_id)},
            ).scalars()
            raw_audit_hashes: list[str] = list(hash_rows)
        for payload in raw_payloads:
            assert secret_reason.encode() not in bytes(payload)
        for payload_hash in raw_audit_hashes:
            assert secret_reason not in payload_hash
