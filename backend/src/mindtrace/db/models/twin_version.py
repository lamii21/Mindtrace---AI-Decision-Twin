"""The ``twin_version`` table (AG-6, tier B - immutable once written).

No encrypted columns (ADR-009): ``trait_snapshot``/``weights``/
``dispositions`` are numeric posterior parameters and MCDA-ready weights -
the same plaintext classification M7 already established for
``simulation.model_confidence``/``extraction.factors``. Strictly append-only
(migration 0004): ``mindtrace_app`` has no ``UPDATE``/``DELETE`` grant here
at all.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mindtrace.db.base import Base


class TwinVersionModel(Base):
    """One immutable snapshot of a twin's preference posterior."""

    __tablename__ = "twin_version"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    twin_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("twin.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    trait_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    weights: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    dispositions: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    engine_version: Mapped[str] = mapped_column(Text, nullable=False)
    projection_version: Mapped[str] = mapped_column(Text, nullable=False)
    factor_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    trait_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
