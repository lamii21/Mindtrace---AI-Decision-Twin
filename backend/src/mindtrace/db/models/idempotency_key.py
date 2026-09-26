"""The ``idempotency_key`` table (M6-API, ``docs/api/08`` s1).

Stores only a fingerprint and the id of the resource an idempotent request
created - never a cached response body, which for ``POST /v1/decisions``
would mean caching plaintext prose outside the encrypted columns ADR-009
classifies it under. A replay re-fetches the real resource through the
normal, decrypting repository path instead.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mindtrace.db.base import Base


class IdempotencyKeyModel(Base):
    """One claimed ``Idempotency-Key`` for one user's one route."""

    __tablename__ = "idempotency_key"
    __table_args__ = (
        UniqueConstraint("user_id", "route", "idempotency_key", name="uq_idempotency_key_scope"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    route: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    response_status: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
