"""Cross-tenant ownership behaviour over HTTP (``docs/api/08`` s1: "a mismatch
is 404, not 403 - don't confirm existence"). Two real users, real PostgreSQL."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from mindtrace.db.session import get_session
from tests.integration.conftest import requires_docker
from tests.support.api_helpers import auth_headers, register_and_login

pytestmark = requires_docker

_MEMORY_BODY = {"kind": "note", "text": "a private memory", "source": "declared"}
_DECISION_BODY = {
    "title": "private decision",
    "category": "career",
    "context": "context",
    "options": [{"id": "a", "label": "A", "body": "body"}],
}


class TestMemoryOwnership:
    def test_user_a_cannot_read_user_bs_memory(self, api_client: TestClient) -> None:
        _email_a, tokens_a = register_and_login(api_client, label="a")
        _email_b, tokens_b = register_and_login(api_client, label="b")
        created = api_client.post(
            "/v1/memories", headers=auth_headers(tokens_b), json=_MEMORY_BODY
        ).json()

        response = api_client.get(
            f"/v1/memories/{created['memory_id']}", headers=auth_headers(tokens_a)
        )
        assert response.status_code == 404

    def test_user_a_cannot_delete_or_forget_user_bs_memory(self, api_client: TestClient) -> None:
        _email_a, tokens_a = register_and_login(api_client, label="a")
        _email_b, tokens_b = register_and_login(api_client, label="b")
        created = api_client.post(
            "/v1/memories", headers=auth_headers(tokens_b), json=_MEMORY_BODY
        ).json()

        response = api_client.delete(
            f"/v1/memories/{created['memory_id']}",
            headers=auth_headers(tokens_a),
            params={"dry_run": "true"},
        )
        assert response.status_code == 404

        # The victim's memory is untouched.
        still_there = api_client.get(
            f"/v1/memories/{created['memory_id']}", headers=auth_headers(tokens_b)
        )
        assert still_there.status_code == 200
        assert still_there.json()["deleted_at"] is None

    def test_user_bs_memory_never_appears_in_user_as_list(self, api_client: TestClient) -> None:
        _email_a, tokens_a = register_and_login(api_client, label="a")
        _email_b, tokens_b = register_and_login(api_client, label="b")
        api_client.post("/v1/memories", headers=auth_headers(tokens_b), json=_MEMORY_BODY)

        response = api_client.get("/v1/memories", headers=auth_headers(tokens_a))
        assert response.json()["items"] == []


class TestDecisionOwnership:
    def test_user_a_cannot_read_user_bs_decision(self, api_client: TestClient) -> None:
        _email_a, tokens_a = register_and_login(api_client, label="a")
        _email_b, tokens_b = register_and_login(api_client, label="b")
        created = api_client.post(
            "/v1/decisions", headers=auth_headers(tokens_b), json=_DECISION_BODY
        ).json()

        response = api_client.get(f"/v1/decisions/{created['id']}", headers=auth_headers(tokens_a))
        assert response.status_code == 404

    def test_user_a_cannot_patch_user_bs_decision(self, api_client: TestClient) -> None:
        _email_a, tokens_a = register_and_login(api_client, label="a")
        _email_b, tokens_b = register_and_login(api_client, label="b")
        created = api_client.post(
            "/v1/decisions", headers=auth_headers(tokens_b), json=_DECISION_BODY
        ).json()

        response = api_client.patch(
            f"/v1/decisions/{created['id']}",
            headers=auth_headers(tokens_a),
            json={"reasoning": "trying to tamper"},
        )
        assert response.status_code == 404

        # The victim's decision is untouched.
        untouched = api_client.get(f"/v1/decisions/{created['id']}", headers=auth_headers(tokens_b))
        assert untouched.json()["reasoning"] is None

    def test_user_bs_decision_never_appears_in_user_as_list(self, api_client: TestClient) -> None:
        _email_a, tokens_a = register_and_login(api_client, label="a")
        _email_b, tokens_b = register_and_login(api_client, label="b")
        api_client.post("/v1/decisions", headers=auth_headers(tokens_b), json=_DECISION_BODY)

        response = api_client.get("/v1/decisions", headers=auth_headers(tokens_a))
        assert response.json()["items"] == []


class TestRawDatabaseIsolation:
    def test_raw_query_without_app_user_id_sees_zero_rows_across_both_users(
        self, api_client: TestClient
    ) -> None:
        _email_a, tokens_a = register_and_login(api_client, label="a")
        _email_b, tokens_b = register_and_login(api_client, label="b")
        api_client.post("/v1/memories", headers=auth_headers(tokens_a), json=_MEMORY_BODY)
        api_client.post("/v1/decisions", headers=auth_headers(tokens_b), json=_DECISION_BODY)

        with get_session() as session:
            memory_rows = session.execute(text("SELECT id FROM memory")).all()
            decision_rows = session.execute(text("SELECT id FROM decision")).all()
        assert memory_rows == []
        assert decision_rows == []
