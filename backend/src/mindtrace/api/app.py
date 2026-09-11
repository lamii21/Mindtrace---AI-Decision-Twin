"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from mindtrace import __version__
from mindtrace.api.routers import health


def create_app() -> FastAPI:
    """Build the MINDTRACE API.

    M1 wires a single router. No middleware, no database, no auth, no LLM.
    """
    app = FastAPI(
        title="MINDTRACE API",
        version=__version__,
        summary="An auditable AI decision twin.",
    )
    app.include_router(health.router)
    return app


app = create_app()
