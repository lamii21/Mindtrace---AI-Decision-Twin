"""The ``twin`` table (AG-6).

Thin: no encrypted columns (``name`` is a short user label, same
classification as ``decision.category``). ``next_twin_version`` is the
atomic version-allocation counter (migration 0004's own docstring) -
``mindtrace_app`` has ``UPDATE`` on this table for that one purpose only.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from mindtrace.db.base import Base


class TwinModel(Base):
    """One user's twin - at most one per user in M8."""

    __tablename__ = "twin"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    next_twin_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
