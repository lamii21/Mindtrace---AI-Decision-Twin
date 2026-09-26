"""The ``user_data_key`` table: wrapped per-user DEKs, never a raw key (ADR-009).

``wrapped_dek``/``nonce`` are the output of
``security.keyring.EnvironmentKeyProvider.wrap_dek`` - opaque bytes to this
module. ``destroyed_at`` is how crypto-shredding is represented: setting it
makes every row this DEK ever encrypted permanently unrecoverable, without
touching a single ``memory_event``/``memory``/``decision`` row (ADR-009).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, LargeBinary, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mindtrace.db.base import Base


class UserDataKeyModel(Base):
    """One generation of one user's wrapped DEK."""

    __tablename__ = "user_data_key"
    __table_args__ = (UniqueConstraint("user_id", "key_version", name="uq_user_data_key_version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    key_version: Mapped[int] = mapped_column(nullable=False)
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    destroyed_at: Mapped[datetime | None] = mapped_column(nullable=True)
