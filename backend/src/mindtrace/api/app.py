"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from mindtrace import __version__
from mindtrace.api.errors import register_exception_handlers
from mindtrace.api.routers import auth, decisions, elicitation, evidence, health, memories, simulate


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
    app.include_router(elicitation.router)
    app.include_router(evidence.router)
    register_exception_handlers(app)
    return app


app = create_app()
