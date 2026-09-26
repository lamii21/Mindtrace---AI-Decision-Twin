"""Shared helpers for API integration tests (M6-API)."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

DEFAULT_PASSWORD = "correct horse battery staple"


def unique_email(label: str = "user") -> str:
    """A syntactically-valid, non-reserved-domain email unique to this call.

    ``example.com``/``.test``/``.invalid`` are RFC 2606 reserved domains that
    ``email-validator`` (pydantic's ``EmailStr``) rejects outright - this
    domain is fictitious but not in the reserved set.
    """
    return f"{label}-{uuid4().hex}@mindtrace-integration-tests.dev"


def register(
    client: TestClient, *, email: str | None = None, password: str = DEFAULT_PASSWORD
) -> dict[str, object]:
    email = email or unique_email()
    response = client.post("/v1/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    body["_password"] = password
    return body


def login(client: TestClient, *, email: str, password: str = DEFAULT_PASSWORD) -> dict[str, str]:
    response = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    result: dict[str, str] = response.json()
    return result


def register_and_login(client: TestClient, *, label: str = "user") -> tuple[str, dict[str, str]]:
    """Register a fresh user and log in. Returns ``(email, tokens)``."""
    email = unique_email(label)
    register(client, email=email)
    tokens = login(client, email=email)
    return email, tokens


def auth_headers(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}
