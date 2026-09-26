"""The ``consent_record`` table (AG-1). Append-only - no update path ever writes here."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from mindtrace.db.base import Base


class ConsentRecordModel(Base):
    """One immutable statement of consent (or its withdrawal) for one scope."""

    __tablename__ = "consent_record"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(nullable=False)
