"""The ``audit_log`` table (M9; ``docs/architecture/02`` cross-cutting). Append-only, tier A."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from mindtrace.db.base import Base


class AuditLogModel(Base):
    """One immutable accountability record. No ``UPDATE``/``DELETE`` grant exists for this table."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    engine_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_hash: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(nullable=False)
