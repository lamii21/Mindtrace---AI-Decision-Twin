"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from mindtrace import __version__
from mindtrace.api.errors import register_exception_handlers
from mindtrace.api.routers import auth, decisions, health, memories, simulate


def create_app() -> FastAPI:
    """Build the MINDTRACE API.

    M6-API wires auth/memories/decisions. M7 adds `/v1/simulate` +
    `/v1/simulations/{id}`, the one HTTP-reachable path that calls
    `orchestration.simulate()` (via `services.decision_service`) - no other
    route in this app does, and no route calls an engine directly.
    """
    app = FastAPI(
        title="MINDTRACE API",
        version=__version__,
        summary="An auditable AI decision twin.",
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(memories.router)
    app.include_router(decisions.router)
    app.include_router(simulate.router, prefix="/v1")
    register_exception_handlers(app)
    return app


app = create_app()
