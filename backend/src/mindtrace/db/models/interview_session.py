"""The ``interview_session`` table - thin, mutable operational state.

Not a tier-A/B record: the answers themselves are ``elicitation_answered``
events (0001's ``memory_event``, already encrypted); this row only tracks
that a session exists, which twin/version it resolved to, and whether it
has been finalized. No encrypted columns - nothing here is user-authored
prose (ids and timestamps only).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from mindtrace.db.base import Base


class InterviewSessionModel(Base):
    """One in-flight or completed Twin Interview session."""

    __tablename__ = "interview_session"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    twin_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("twin.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resulting_twin_version_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    interview_noise: Mapped[float | None] = mapped_column(Float, nullable=True)
