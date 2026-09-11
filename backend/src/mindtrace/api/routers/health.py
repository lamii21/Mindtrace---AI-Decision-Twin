"""Liveness endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from mindtrace import __version__
from mindtrace.api.schemas.health import HealthResponse

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
def health() -> HealthResponse:
    """Report that the process is up. No dependencies are touched."""
    return HealthResponse(service="mindtrace", version=__version__)
