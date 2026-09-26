"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from mindtrace import __version__
from mindtrace.api.errors import register_exception_handlers
from mindtrace.api.routers import auth, decisions, health, memories


def create_app() -> FastAPI:
    """Build the MINDTRACE API.

    M6-API wires auth/memories/decisions. No `/v1/simulate` route exists -
    that is M7's; no orchestration, engine, or LLM call happens anywhere in
    this app (M6-API planning s2's hard scope boundary).
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
    register_exception_handlers(app)
    return app


app = create_app()
