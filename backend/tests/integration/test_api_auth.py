"""``/v1/auth/*`` end to end against real PostgreSQL (M6-API planning s15)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from mindtrace.db.repositories.user_repository import find_user_by_email
from mindtrace.db.session import user_scoped_session
from tests.integration.conftest import requires_docker
from tests.support.api_helpers import (
    DEFAULT_PASSWORD,
    auth_headers,
    login,
    register,
    register_and_login,
    unique_email,
)

pytestmark = requires_docker


class TestRegister:
    def test_register_returns_201_with_no_password_in_the_body(
        self, api_client: TestClient
    ) -> None:
        body = register(api_client)
        assert "password" not in body
        assert "password_hash" not in body

    def test_duplicate_email_is_rejected(self, api_client: TestClient) -> None:
        email = unique_email()
        register(api_client, email=email)
        response = api_client.post(
            "/v1/auth/register", json={"email": email, "password": DEFAULT_PASSWORD}
        )
        assert response.status_code == 409
        assert response.headers["content-type"] == "application/problem+json"

    def test_short_password_is_rejected_with_422(self, api_client: TestClient) -> None:
        response = api_client.post(
            "/v1/auth/register", json={"email": unique_email(), "password": "short"}
        )
        assert response.status_code == 422
        assert response.json()["errors"]

    def test_password_is_stored_as_an_argon2_hash(self, api_client: TestClient) -> None:
        email = unique_email()
        register(api_client, email=email)
        credentials = find_user_by_email(email)
        assert credentials is not None
        assert credentials.password_hash.startswith("$argon2id$")


class TestLogin:
    def test_login_success_returns_a_token_pair(self, api_client: TestClient) -> None:
        email = unique_email()
        register(api_client, email=email)
        tokens = login(api_client, email=email)
        assert tokens["token_type"] == "bearer"
        assert tokens["access_token"]
        assert tokens["refresh_token"]

    def test_wrong_password_is_rejected(self, api_client: TestClient) -> None:
        email = unique_email()
        register(api_client, email=email)
        response = api_client.post(
            "/v1/auth/login", json={"email": email, "password": "the wrong password"}
        )
        assert response.status_code == 401

    def test_unknown_email_is_rejected_identically_to_wrong_password(
        self, api_client: TestClient
    ) -> None:
        response = api_client.post(
            "/v1/auth/login", json={"email": unique_email(), "password": DEFAULT_PASSWORD}
        )
        assert response.status_code == 401


class TestAccessToken:
    def test_missing_token_is_rejected(self, api_client: TestClient) -> None:
        assert api_client.get("/v1/auth/me").status_code in (401, 403)

    def test_malformed_token_is_rejected(self, api_client: TestClient) -> None:
        response = api_client.get(
            "/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
        )
        assert response.status_code == 401

    def test_wrong_scheme_is_rejected(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        response = api_client.get(
            "/v1/auth/me", headers={"Authorization": f"Basic {tokens['access_token']}"}
        )
        assert response.status_code in (401, 403)

    def test_refresh_token_is_never_accepted_as_an_access_token(
        self, api_client: TestClient
    ) -> None:
        _email, tokens = register_and_login(api_client)
        response = api_client.get(
            "/v1/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
        )
        assert response.status_code == 401


class TestRefreshRotation:
    def test_refresh_issues_a_new_working_token_pair(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        response = api_client.post(
            "/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert response.status_code == 200
        new_tokens = response.json()
        me = api_client.get("/v1/auth/me", headers=auth_headers(new_tokens))
        assert me.status_code == 200

    def test_the_old_refresh_token_is_consumed_by_rotation(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        api_client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        replay = api_client.post(
            "/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert replay.status_code == 401

    def test_reusing_a_consumed_token_revokes_the_entire_family(
        self, api_client: TestClient
    ) -> None:
        _email, tokens = register_and_login(api_client)
        first = api_client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        new_tokens = first.json()

        # Reuse of the now-consumed original token.
        api_client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

        # The legitimately-issued *next* token must also be rejected now -
        # the whole family was revoked, not just the reused token.
        second = api_client.post(
            "/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]}
        )
        assert second.status_code == 401

    def test_unknown_refresh_token_is_rejected(self, api_client: TestClient) -> None:
        response = api_client.post("/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})
        assert response.status_code == 401


class TestLogout:
    def test_logout_revokes_the_refresh_token(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        logout_response = api_client.post("/v1/auth/logout", headers=auth_headers(tokens))
        assert logout_response.status_code == 204

        refresh_response = api_client.post(
            "/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert refresh_response.status_code == 401

    def test_logout_requires_authentication(self, api_client: TestClient) -> None:
        assert api_client.post("/v1/auth/logout").status_code in (401, 403)


class TestMe:
    def test_me_returns_the_authenticated_users_own_identity(self, api_client: TestClient) -> None:
        email, tokens = register_and_login(api_client)
        response = api_client.get("/v1/auth/me", headers=auth_headers(tokens))
        assert response.status_code == 200
        assert response.json()["email"] == email


class TestConsent:
    def test_setting_consent_is_reflected_in_me(self, api_client: TestClient) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        response = api_client.put(
            "/v1/auth/consent",
            headers=headers,
            json={"scope": "store_memories", "granted": True},
        )
        assert response.status_code == 200

        me = api_client.get("/v1/auth/me", headers=headers).json()
        consents = {c["scope"]: c["granted"] for c in me["consents"]}
        assert consents["store_memories"] is True

    def test_changing_consent_appends_a_new_record_reflected_as_the_latest(
        self, api_client: TestClient
    ) -> None:
        _email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        api_client.put(
            "/v1/auth/consent", headers=headers, json={"scope": "run_inference", "granted": True}
        )
        time.sleep(0.01)
        api_client.put(
            "/v1/auth/consent", headers=headers, json={"scope": "run_inference", "granted": False}
        )
        me = api_client.get("/v1/auth/me", headers=headers).json()
        consents = {c["scope"]: c["granted"] for c in me["consents"]}
        assert consents["run_inference"] is False

    def test_consent_history_is_append_only_at_the_database_level(
        self, api_client: TestClient
    ) -> None:
        email, tokens = register_and_login(api_client)
        headers = auth_headers(tokens)
        api_client.put(
            "/v1/auth/consent", headers=headers, json={"scope": "store_memories", "granted": True}
        )
        credentials = find_user_by_email(email)
        assert credentials is not None
        with (
            pytest.raises(DBAPIError, match="permission denied"),
            user_scoped_session(credentials.id) as session,
        ):
            session.execute(
                text("UPDATE consent_record SET granted = false WHERE user_id = :uid"),
                {"uid": str(credentials.id)},
            )
