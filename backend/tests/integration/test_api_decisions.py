"""``/v1/decisions`` end to end against real PostgreSQL (M6-API planning s15).

No ``/v1/simulate`` route exists to call, and nothing here ever imports
``mindtrace.orchestration`` - confirmed structurally by
``test_api_openapi.py``, not just by omission here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from tests.integration.conftest import requires_docker
from tests.support.api_helpers import auth_headers, register_and_login

pytestmark = requires_docker

_VALID_BODY = {
    "title": "Take the backend internship?",
    "category": "career",
    "context": "Pays well and uses the stack I want to learn.",
    "options": [{"id": "accept", "label": "Accept", "body": "Take the offer."}],
}


class TestCreateDecision:
    def test_create_returns_201_as_draft(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        response = api_client.post("/v1/decisions", headers=auth_headers(tokens), json=_VALID_BODY)
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "draft"
        assert body["extracted_factors"] is None
        assert body["latest_prediction"] is None
        assert body["outcome"] is None

    def test_retrospective_decision_with_decided_at_and_chosen_option_is_committed(
        self, api_client: TestClient
    ) -> None:
        _email, tokens = register_and_login(api_client)
        body = {
            **_VALID_BODY,
            "decided_at": datetime.now(UTC).isoformat(),
            "chosen_option": "accept",
        }
        response = api_client.post("/v1/decisions", headers=auth_headers(tokens), json=body)
        assert response.status_code == 201
        assert response.json()["status"] == "committed"

    def test_chosen_option_not_in_options_is_rejected(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        body = {**_VALID_BODY, "chosen_option": "does-not-exist"}
        response = api_client.post("/v1/decisions", headers=auth_headers(tokens), json=body)
        assert response.status_code == 422

    def test_zero_options_is_rejected_by_the_schema(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        response = api_client.post(
            "/v1/decisions", headers=auth_headers(tokens), json={**_VALID_BODY, "options": []}
        )
        assert response.status_code == 422

    def test_create_requires_authentication(self, api_client: TestClient) -> None:
        assert api_client.post("/v1/decisions", json=_VALID_BODY).status_code in (401, 403)


class TestListAndGetDecisions:
    def test_list_returns_created_decisions(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        api_client.post("/v1/decisions", headers=headers, json=_VALID_BODY)
        response = api_client.get("/v1/decisions", headers=headers)
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    def test_filter_by_category(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        api_client.post(
            "/v1/decisions", headers=headers, json={**_VALID_BODY, "category": "career"}
        )
        api_client.post(
            "/v1/decisions",
            headers=headers,
            json={**_VALID_BODY, "title": "other", "category": "purchase"},
        )
        response = api_client.get("/v1/decisions", headers=headers, params={"category": "purchase"})
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["category"] == "purchase"

    def test_get_unknown_decision_is_404(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        response = api_client.get(f"/v1/decisions/{uuid.uuid4()}", headers=auth_headers(tokens))
        assert response.status_code == 404


class TestPatchDecision:
    def test_setting_chosen_option_and_status_commits_it(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        created = api_client.post("/v1/decisions", headers=headers, json=_VALID_BODY).json()

        response = api_client.patch(
            f"/v1/decisions/{created['id']}",
            headers=headers,
            json={"chosen_option": "accept", "status": "committed"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "committed"
        assert body["chosen_option"] == "accept"
        assert body["decided_at"] is not None

    def test_invalid_chosen_option_is_rejected(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        created = api_client.post("/v1/decisions", headers=headers, json=_VALID_BODY).json()

        response = api_client.patch(
            f"/v1/decisions/{created['id']}",
            headers=headers,
            json={"chosen_option": "not-a-real-option"},
        )
        assert response.status_code == 422

    def test_setting_status_to_simulated_directly_is_rejected(self, api_client: TestClient) -> None:
        """M6 cannot honestly produce `simulated` - that requires M7's engine."""
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        created = api_client.post("/v1/decisions", headers=headers, json=_VALID_BODY).json()

        response = api_client.patch(
            f"/v1/decisions/{created['id']}", headers=headers, json={"status": "simulated"}
        )
        assert response.status_code == 409

    def test_archiving_then_patching_again_is_rejected(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        created = api_client.post("/v1/decisions", headers=headers, json=_VALID_BODY).json()
        api_client.patch(
            f"/v1/decisions/{created['id']}", headers=headers, json={"status": "archived"}
        )

        response = api_client.patch(
            f"/v1/decisions/{created['id']}", headers=headers, json={"status": "committed"}
        )
        assert response.status_code == 409

    def test_patch_unknown_decision_is_404(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        response = api_client.patch(
            f"/v1/decisions/{uuid.uuid4()}", headers=auth_headers(tokens), json={"reasoning": "x"}
        )
        assert response.status_code == 404


class TestSimulationsAlwaysEmpty:
    def test_simulations_list_is_always_empty_in_m6(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        created = api_client.post("/v1/decisions", headers=headers, json=_VALID_BODY).json()

        response = api_client.get(f"/v1/decisions/{created['id']}/simulations", headers=headers)
        assert response.status_code == 200
        assert response.json() == {"items": [], "next_cursor": None}

    def test_simulations_of_an_unowned_decision_is_404(self, api_client: TestClient) -> None:
        _email_a, tokens_a = register_and_login(api_client, label="a")
        _email_b, tokens_b = register_and_login(api_client, label="b")
        created = api_client.post(
            "/v1/decisions", headers=auth_headers(tokens_a), json=_VALID_BODY
        ).json()

        response = api_client.get(
            f"/v1/decisions/{created['id']}/simulations", headers=auth_headers(tokens_b)
        )
        assert response.status_code == 404


class TestIdempotency:
    def test_same_key_and_body_returns_the_same_resource(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = {**auth_headers(tokens), "Idempotency-Key": "fixed-key-1"}
        first = api_client.post("/v1/decisions", headers=headers, json=_VALID_BODY)
        second = api_client.post("/v1/decisions", headers=headers, json=_VALID_BODY)
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["id"] == second.json()["id"]

    def test_same_key_different_body_is_a_409_conflict(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = {**auth_headers(tokens), "Idempotency-Key": "fixed-key-2"}
        first = api_client.post("/v1/decisions", headers=headers, json=_VALID_BODY)
        second = api_client.post(
            "/v1/decisions", headers=headers, json={**_VALID_BODY, "title": "a different title"}
        )
        assert first.status_code == 201
        assert second.status_code == 409
