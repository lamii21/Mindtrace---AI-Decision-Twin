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


def test_app_has_no_other_business_routes_yet() -> None:
    app = create_app()
    framework_paths = {"/health", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    business_paths = paths - framework_paths
    assert business_paths == set(), f"unexpected routes in M1: {business_paths}"
