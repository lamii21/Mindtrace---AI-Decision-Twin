"""Refresh-token rotation state (M6-API, ADR-008 T9).

Not an event-sourced or encrypted concept - a token hash is not "user
content" in ADR-009's sense (it is already a one-way digest, same class as
``password_hash``), and rotation state is inherently mutable operational
state (a token is consumed/revoked in place), not an append-only fact.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from mindtrace.domain.ids import UserId

_FrozenModel = ConfigDict(frozen=True, extra="forbid")


class RefreshToken(BaseModel):
    """One issued refresh token: a link in a rotation family.

    ``family_id`` is shared by every token descended from one login; reusing
    an already-``consumed_at``/``revoked_at`` token revokes the whole family
    (M6-API planning s5).
    """

    model_config = _FrozenModel

    id: UUID
    user_id: UserId
    family_id: UUID
    token_hash: str
    issued_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None
    revoked_at: datetime | None = None
    replaced_by: UUID | None = None

    @property
    def is_active(self) -> bool:
        """Neither consumed nor revoked.

        Expiry is not checked here - that needs a caller-supplied ``now``
        (Invariant A).
        """
        return self.consumed_at is None and self.revoked_at is None
