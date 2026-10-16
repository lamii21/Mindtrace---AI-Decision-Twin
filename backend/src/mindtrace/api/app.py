"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mindtrace import __version__
from mindtrace.api.errors import register_exception_handlers
from mindtrace.api.routers import auth, decisions, elicitation, evidence, health, memories, simulate
from mindtrace.config import get_settings
from mindtrace.db.session import configure_engine


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure ``db.session``'s process-wide engine from ``Settings`` on real startup.

    ``db.session.configure_engine``'s own docstring names this exact hook
    ("test fixtures, a future application startup hook") - test fixtures
    already call it directly, so this only matters for a real ASGI server
    (``uvicorn mindtrace.api.app:app``); ``TestClient`` never runs a
    ``lifespan`` unless used as a context manager (``with TestClient(app)
    as client:``), which nothing in this codebase does, so no existing test
    is affected by adding this. Skipped when ``database_url`` is unset -
    ``test_client_can_be_built_with_no_database_configured`` documents that
    building the app and reading ``/openapi.json`` must never require one.
    """
    settings = get_settings()
    if settings.database_url is not None:
        configure_engine(settings.database_url)
    yield


def create_app() -> FastAPI:
    """Build the MINDTRACE API.

    M6-API wires auth/memories/decisions. M7 adds `/v1/simulate` +
    `/v1/simulations/{id}`, the one HTTP-reachable path that calls
    `orchestration.simulate()` (via `services.decision_service`) - no other
    route in this app does, and no route calls an engine directly. M8 adds
    `/v1/elicitation/*` (the fixed-order Twin Interview) - no Active
    Elicitation/EIG, no `/v1/twins*` retrieval routes (still deferred). M9
    adds `GET /v1/evidence/{type}/{id}` and
    `POST /v1/beliefs/{type}/{id}:dispute`, plus richer `DELETE /v1/memories/
    {id}` re-derivation - no Contradiction Engine, no Evaluation Engine,
    still no `/v1/twins*`/outcome-recording (out of this milestone's
    documented scope).

    CORS is restricted to `Settings.cors_origins` (default: the frontend's
    own dev origin, `http://localhost:3000`) - never a wildcard, since every
    route but register/login requires a bearer token and the frontend sends
    it via `Authorization`, not a cookie; `allow_credentials=True` matters
    only if a future browser flow ever needs cookies, but a specific
    origin allowlist is required either way (browsers reject `allow_origins
    = ["*"]` together with credentialed requests).
    """
    app = FastAPI(
        title="MINDTRACE API",
        version=__version__,
        summary="An auditable AI decision twin.",
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(memories.router)
    app.include_router(decisions.router)
    app.include_router(simulate.router, prefix="/v1")
    app.include_router(elicitation.router)
    app.include_router(evidence.router)
    register_exception_handlers(app)
    return app


app = create_app()
