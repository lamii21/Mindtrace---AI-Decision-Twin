"""The ``prediction`` table (AG-8, M7-scoped).

``predicted_decision`` is the confidence-gated, product-level label composed
by ``services/decision_service.py`` - not M3's raw ``DecisionResult.label``
(that stays inside ``simulation.results``, untouched). ``twin_version_id``/
``credible_interval`` are always ``NULL`` in M7 (no ``Twin``/``TwinVersion``
yet - M8; no trait posterior sampling yet - M4's own documented limitation).
Plaintext throughout, same reasoning as ``simulation.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mindtrace.db.base import Base


class PredictionModel(Base):
    """The immutable row the Evaluation Engine (M9) will score."""

    __tablename__ = "prediction"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    decision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("decision.id"), nullable=False)
    simulation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("simulation.id"), nullable=False)
    twin_version_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    predicted_decision: Mapped[str] = mapped_column(Text, nullable=False)
    uncertain_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    predicted_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    credible_interval: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    factor_contributions: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    margin: Mapped[float] = mapped_column(Float, nullable=False)
    engine_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
