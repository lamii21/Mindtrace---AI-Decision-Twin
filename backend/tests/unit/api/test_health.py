"""Tests for the minimal FastAPI application and its ``/health`` route."""

from __future__ import annotations

from fastapi.testclient import TestClient

from mindtrace import __version__
from mindtrace.api.app import create_app


def test_health_returns_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "mindtrace", "version": __version__}


def test_health_response_is_deterministic_across_calls() -> None:
    client = TestClient(create_app())
    first = client.get("/health").json()
    second = client.get("/health").json()
    assert first == second


def test_app_exposes_exactly_the_current_business_routes() -> None:
    """As of M7, auth/memories/decisions/simulate routers are wired in.

    Still guards against accidentally adding anything from M8+ (twins,
    elicitation, evaluation, contradictions).

    Reads the OpenAPI spec rather than walking ``app.routes`` directly:
    FastAPI's router composition wraps included routers in an internal
    ``_IncludedRouter`` that does not expose a flat ``.path`` per route.
    """
    app = create_app()
    paths = set(app.openapi()["paths"].keys())
    business_paths = paths - {"/health"}
    assert business_paths == {
        "/v1/auth/register",
        "/v1/auth/login",
        "/v1/auth/refresh",
        "/v1/auth/logout",
        "/v1/auth/me",
        "/v1/auth/consent",
        "/v1/memories",
        "/v1/memories/{memory_id}",
        "/v1/decisions",
        "/v1/decisions/{decision_id}",
        "/v1/decisions/{decision_id}/simulations",
        "/v1/simulate",
        "/v1/simulations/{simulation_id}",
    }
