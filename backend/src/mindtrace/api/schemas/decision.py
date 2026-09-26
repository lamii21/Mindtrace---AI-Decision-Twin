"""Decision request/response DTOs (``docs/api/08`` s4). Field names/shapes are exact.

``DecisionSummary`` is documented (``Page[DecisionSummary]``) without its own
field list separate from ``DecisionOut`` - reusing ``DecisionOut``'s fields
avoids inventing an undocumented narrower shape (M6-API planning).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_FrozenExtraForbid = ConfigDict(extra="forbid")

DecisionCategoryIn = Literal["career", "education", "project", "purchase", "relationship", "other"]
DecisionStatusOut = Literal["draft", "simulated", "committed", "archived"]


class OptionIn(BaseModel):
    """One named option under consideration."""

    model_config = _FrozenExtraForbid

    id: str
    label: str
    body: str


class DecisionCreate(BaseModel):
    """``POST /v1/decisions`` request body."""

    model_config = _FrozenExtraForbid

    title: str
    category: DecisionCategoryIn
    context: str
    options: list[OptionIn] = Field(min_length=1, max_length=6)
    high_stakes: bool = False
    decided_at: datetime | None = None
    chosen_option: str | None = None


class DecisionOut(BaseModel):
    """``POST``/``GET``/``PATCH /v1/decisions[/{id}]`` response body.

    ``extracted_factors``/``extraction_model_run_id``/``latest_prediction``/
    ``outcome`` are always ``null`` in M6 - they are M7+/M8+ fields with no
    producing engine wired to the API yet.
    """

    model_config = _FrozenExtraForbid

    id: UUID
    title: str
    category: str
    context: str
    options: list[OptionIn]
    status: DecisionStatusOut
    extracted_factors: dict[str, dict[str, object]] | None
    extraction_model_run_id: UUID | None
    chosen_option: str | None
    reasoning: str | None
    decided_at: datetime | None
    latest_prediction: dict[str, object] | None
    outcome: dict[str, object] | None
    created_at: datetime


DecisionSummary = DecisionOut


class DecisionPatch(BaseModel):
    """``PATCH /v1/decisions/{id}`` request body."""

    model_config = _FrozenExtraForbid

    chosen_option: str | None = None
    reasoning: str | None = None
    status: DecisionStatusOut | None = None


class SimulationSummary(BaseModel):
    """One item of ``GET /v1/decisions/{id}/simulations``.

    Never populated in M6, since no ``Simulation`` table exists yet (M7).
    """

    model_config = _FrozenExtraForbid

    simulation_id: UUID
    created_at: datetime
