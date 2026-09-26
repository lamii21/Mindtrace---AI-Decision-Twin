"""The ``memory_event`` table - Tier A source of truth (ADR-001, AG-2).

Append-only by construction: no ORM method here ever issues an ``UPDATE`` or
``DELETE`` against this table, and the application DB role's grants enforce
the same thing independently (``migrations/0001_initial.py`` ``REVOKE``s
them - Python discipline alone is not the control, per M6-Persistence
planning s21). ``payload`` is the encrypted envelope (ADR-009); every other
column stays plaintext because the append-only ordering guarantee
(``UNIQUE(user_id, seq)``) and every documented query/filter depend on it
being real, indexed SQL, not ciphertext.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, LargeBinary, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mindtrace.db.base import Base


class MemoryEventModel(Base):
    """One immutable, ordered fact in a user's event stream."""

    __tablename__ = "memory_event"
    __table_args__ = (UniqueConstraint("user_id", "seq", name="uq_memory_event_user_seq"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    seq: Mapped[int] = mapped_column(nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    causation_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
