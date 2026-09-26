"""The user aggregate root (``docs/architecture/02-domain-model.md`` AG-1).

An operational record, not an event-sourced projection (M2 s1's tier
distinction): mutable in the narrow, audited ways AG-1 describes, never
folded from an event stream. ``password_hash`` is stored here because AG-1
names it as a field of the aggregate; nothing in this milestone hashes a
password or issues a token (that is the auth slice's job) - this type only
carries the value through persistence.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from mindtrace.domain.enums import UserStatus
from mindtrace.domain.ids import UserId

_FrozenModel = ConfigDict(frozen=True, extra="forbid")


class User(BaseModel):
    """One MINDTRACE account.

    ``data_key_ref`` is a pointer into the keyring - the current
    ``user_data_key.key_version`` for this user - never the key material
    itself (ADR-009).
    """

    model_config = _FrozenModel

    id: UserId
    email: str
    password_hash: str
    status: UserStatus
    data_key_ref: int
    created_at: datetime
    deleted_at: datetime | None = None
