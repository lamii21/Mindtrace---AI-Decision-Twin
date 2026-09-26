"""``/v1/memories`` end to end against real PostgreSQL (M6-API planning s15)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from mindtrace.db.repositories.user_repository import find_user_by_email
from mindtrace.db.session import user_scoped_session
from tests.integration.conftest import requires_docker
from tests.support.api_helpers import auth_headers, register_and_login

pytestmark = requires_docker

_VALID_BODY = {"kind": "note", "text": "I value autonomy above salary.", "source": "declared"}


class TestCreateMemory:
    def test_create_returns_202_with_a_memory_id(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        response = api_client.post("/v1/memories", headers=auth_headers(tokens), json=_VALID_BODY)
        assert response.status_code == 202
        body = response.json()
        assert body["projection"] == "done"
        assert body["memory_id"] == body["memory_event_id"]

    def test_create_requires_authentication(self, api_client: TestClient) -> None:
        assert api_client.post("/v1/memories", json=_VALID_BODY).status_code in (401, 403)

    def test_invalid_body_returns_422_problem_json(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        response = api_client.post(
            "/v1/memories", headers=auth_headers(tokens), json={"kind": "note"}
        )
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"

    def test_unknown_field_is_rejected_extra_forbid(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        response = api_client.post(
            "/v1/memories", headers=auth_headers(tokens), json={**_VALID_BODY, "bogus": 1}
        )
        assert response.status_code == 422

    def test_seq_is_visible_via_the_projected_get(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        first = api_client.post("/v1/memories", headers=headers, json=_VALID_BODY).json()
        second = api_client.post(
            "/v1/memories", headers=headers, json={**_VALID_BODY, "text": "second memory"}
        ).json()
        first_out = api_client.get(f"/v1/memories/{first['memory_id']}", headers=headers).json()
        second_out = api_client.get(f"/v1/memories/{second['memory_id']}", headers=headers).json()
        assert first_out["origin_event_seq"] == 1
        assert second_out["origin_event_seq"] == 2


class TestEncryptionBoundary:
    def test_response_is_plaintext_but_the_raw_db_row_is_not(self, api_client: TestClient) -> None:
        email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        secret_text = "a very specific secret memory: xyzzy-plugh-42"
        created = api_client.post(
            "/v1/memories", headers=headers, json={**_VALID_BODY, "text": secret_text}
        ).json()

        fetched = api_client.get(f"/v1/memories/{created['memory_id']}", headers=headers).json()
        assert fetched["text"] == secret_text

        credentials = find_user_by_email(email)
        assert credentials is not None
        with user_scoped_session(credentials.id) as session:
            raw_content: bytes = session.execute(
                text("SELECT content FROM memory WHERE id = :id"), {"id": created["memory_id"]}
            ).scalar_one()
            raw_payload: bytes = session.execute(
                text("SELECT payload FROM memory_event WHERE id = :id"),
                {"id": created["memory_event_id"]},
            ).scalar_one()
        assert secret_text.encode("utf-8") not in bytes(raw_content)
        assert secret_text.encode("utf-8") not in bytes(raw_payload)


class TestListAndGetMemories:
    def test_list_returns_created_memories(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        api_client.post("/v1/memories", headers=headers, json=_VALID_BODY)
        response = api_client.get("/v1/memories", headers=headers)
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_filter_by_source(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        api_client.post("/v1/memories", headers=headers, json={**_VALID_BODY, "source": "declared"})
        api_client.post(
            "/v1/memories",
            headers=headers,
            json={**_VALID_BODY, "text": "observed one", "source": "observed"},
        )
        response = api_client.get("/v1/memories", headers=headers, params={"source": "observed"})
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["source"] == "observed"

    def test_get_unknown_memory_is_404(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        response = api_client.get(f"/v1/memories/{uuid.uuid4()}", headers=auth_headers(tokens))
        assert response.status_code == 404


class TestDeleteMemory:
    def test_dry_run_returns_a_plan_without_deleting(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        created = api_client.post("/v1/memories", headers=headers, json=_VALID_BODY).json()

        plan = api_client.delete(
            f"/v1/memories/{created['memory_id']}", headers=headers, params={"dry_run": "true"}
        )
        assert plan.status_code == 200
        assert plan.json()["reversible"] is False
        assert plan.json()["target_memory_ids"] == [created["memory_id"]]

        still_there = api_client.get(f"/v1/memories/{created['memory_id']}", headers=headers)
        assert still_there.status_code == 200
        assert still_there.json()["deleted_at"] is None

    def test_applying_deletion_marks_the_memory_deleted(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        created = api_client.post("/v1/memories", headers=headers, json=_VALID_BODY).json()

        applied = api_client.delete(
            f"/v1/memories/{created['memory_id']}", headers=headers, params={"dry_run": "false"}
        )
        assert applied.status_code == 202
        assert "job_id" in applied.json()

        after = api_client.get(f"/v1/memories/{created['memory_id']}", headers=headers)
        assert after.json()["deleted_at"] is not None


class TestIdempotency:
    def test_same_key_and_body_returns_the_same_resource(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = {**auth_headers(tokens), "Idempotency-Key": "fixed-key-1"}
        first = api_client.post("/v1/memories", headers=headers, json=_VALID_BODY)
        second = api_client.post("/v1/memories", headers=headers, json=_VALID_BODY)
        assert first.status_code == 202
        assert second.status_code == 202
        assert first.json()["memory_id"] == second.json()["memory_id"]

        listed = api_client.get("/v1/memories", headers=auth_headers(tokens)).json()
        assert len(listed["items"]) == 1

    def test_same_key_different_body_is_a_409_conflict(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = {**auth_headers(tokens), "Idempotency-Key": "fixed-key-2"}
        first = api_client.post("/v1/memories", headers=headers, json=_VALID_BODY)
        second = api_client.post(
            "/v1/memories", headers=headers, json={**_VALID_BODY, "text": "a different memory"}
        )
        assert first.status_code == 202
        assert second.status_code == 409

    def test_idempotency_keys_do_not_collide_across_users(self, api_client: TestClient) -> None:
        _email_a, tokens_a = register_and_login(api_client, label="a")
        _email_b, tokens_b = register_and_login(api_client, label="b")
        same_key_headers_a = {**auth_headers(tokens_a), "Idempotency-Key": "shared-key"}
        same_key_headers_b = {**auth_headers(tokens_b), "Idempotency-Key": "shared-key"}
        response_a = api_client.post("/v1/memories", headers=same_key_headers_a, json=_VALID_BODY)
        response_b = api_client.post("/v1/memories", headers=same_key_headers_b, json=_VALID_BODY)
        assert response_a.status_code == 202
        assert response_b.status_code == 202
        assert response_a.json()["memory_id"] != response_b.json()["memory_id"]
