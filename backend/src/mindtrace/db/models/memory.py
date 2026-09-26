"""The ``memory`` table - Tier C projection (AG-3).

Truncatable/rebuildable by replay; ``id`` equals its originating event's id,
exactly as ``mindtrace.events.projectors.memory`` already mints it - this
table never assigns its own identity. ``content`` is the encrypted envelope
(ADR-009); everything else stays plaintext because
``GET /v1/memories?type=&source=`` (``docs/api/08-api-contracts.md`` s3)
needs to filter on it.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, LargeBinary, Text
from sqlalchemy.orm import Mapped, mapped_column

from mindtrace.db.base import Base


class MemoryModel(Base):
    """One projected memory, current or superseded/deleted.

    No ``created_at`` column: ``domain.memory.Memory`` has none either
    (M2 s9 - "which event established it" is answered by ``origin_event_seq``,
    not a second, redundant timestamp this table would have to keep in sync).
    """

    __tablename__ = "memory"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    origin_event_seq: Mapped[int] = mapped_column(nullable=False)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    deleted_by_event_seq: Mapped[int | None] = mapped_column(nullable=True)
    projector_version: Mapped[str] = mapped_column(Text, nullable=False)
