"""Health-check response DTO."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Deterministic liveness payload. Carries no timestamp and no runtime state."""

    status: Literal["ok"] = "ok"
    service: str
    version: str
