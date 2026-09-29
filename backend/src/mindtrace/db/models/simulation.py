"""The ``simulation`` table (AG-7, M7-scoped: base twin only).

Nothing here is encrypted (ADR-009): every column is categorical or numeric
provenance from M3/M4/M5/M6-A's own already-validated result types - never
the scenario text, never an LLM rationale-span excerpt (M7 planning s7).
``scenario_content_hash`` is the one thing that lets a later reader verify
"was this simulation run against the decision's current context" without
ever storing that context a second time.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mindtrace.db.base import Base


class SimulationModel(Base):
    """One immutable simulation run."""

    __tablename__ = "simulation"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    decision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("decision.id"), nullable=False)
    simulation_version: Mapped[str] = mapped_column(Text, nullable=False)
    scenario_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    extraction: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    twin_configs: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    model_confidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
