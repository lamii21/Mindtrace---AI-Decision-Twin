"""OpenAPI contract verification (M6-API planning s15/s21; M7 planning s23 test N).

Uses a bare ``TestClient`` (no DB session needed - OpenAPI generation never
touches the database), but still gated behind ``requires_docker`` for
consistency with the rest of the integration suite's environment reporting.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from mindtrace.api.app import create_app
from tests.integration.conftest import requires_docker

pytestmark = requires_docker

_EXPECTED_PATHS = {
    "/health",
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


def _spec() -> dict[str, object]:
    return create_app().openapi()


class TestExpectedRoutesExist:
    def test_every_documented_route_is_present(self) -> None:
        spec = _spec()
        paths = set(spec["paths"].keys())  # type: ignore[attr-defined]
        assert paths >= _EXPECTED_PATHS

    def test_simulate_is_post_only(self) -> None:
        spec = _spec()
        methods = set(spec["paths"]["/v1/simulate"].keys())  # type: ignore[index]
        assert methods == {"post"}


class TestNoFutureScopeRoutes:
    def test_no_m8_plus_routes_exist(self) -> None:
        """Twins, elicitation, evaluation, contradictions - all post-M7.

        ``evidence``/``predictions`` are M7 domain *concepts* (persisted,
        used internally by ``/v1/simulate``) but never their own URL path -
        ``GET /v1/evidence/{type}/{id}``/``POST /v1/predictions/{id}/outcome``
        are M9's routes, still absent here.
        """
        spec = _spec()
        paths = spec["paths"].keys()  # type: ignore[attr-defined]
        forbidden_fragments = (
            "twin",
            "elicitation",
            "evidence",
            "evaluation",
            "contradiction",
            "predictions",
        )
        for path in paths:
            for fragment in forbidden_fragments:
                assert fragment not in path.lower(), f"unexpected M8+ route: {path}"

    def test_client_can_be_built_with_no_database_configured(self) -> None:
        """OpenAPI/route registration never touches the database (M6-API planning s11)."""
        client = TestClient(create_app())
        response = client.get("/openapi.json")
        assert response.status_code == 200
