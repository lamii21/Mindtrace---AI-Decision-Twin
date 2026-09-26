"""The ``users`` table (AG-1).

Mirrors ``domain.user.User`` but is not it (``docs/architecture/01-repository-structure.md``
s3: "ORM classes mirror the domain but ARE NOT the domain"). ``next_event_seq``
is infrastructure this table alone owns: the atomic per-user counter
:mod:`mindtrace.db.event_store` allocates ``memory_event.seq`` from (see that
module's docstring for the concurrency argument) - it has no domain-model
counterpart and is never exposed outside ``db/``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from mindtrace.db.base import Base


class UserModel(Base):
    """One row per MINDTRACE account."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    data_key_ref: Mapped[int] = mapped_column(nullable=False)
    next_event_seq: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
