"""Thin coordination for persistence-backed idempotency (``docs/api/08`` s1).

A passthrough to ``db.repositories.idempotency_repository`` - kept as its own
service function (not called directly from routers) purely to preserve "no
``db`` import in routers" as a bright line, even though the underlying logic
is a single repository call.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from mindtrace.db.repositories.idempotency_repository import (
    ClaimResult,
    IdempotencyRecord,
    claim,
    find_existing,
)
from mindtrace.domain.ids import UserId


def check_existing(
    *, user_id: UserId, route: str, idempotency_key: str
) -> IdempotencyRecord | None:
    """The sequential-retry fast path: a prior claim, checked before any work runs."""
    return find_existing(user_id=user_id, route=route, idempotency_key=idempotency_key)


def claim_or_replay(
    *,
    user_id: UserId,
    route: str,
    idempotency_key: str,
    request_fingerprint: str,
    resource_id: UUID,
    response_status: int,
    now: datetime,
) -> ClaimResult:
    """Attempt to claim ``idempotency_key``. See ``ClaimResult`` for the two outcomes."""
    return claim(
        user_id=user_id,
        route=route,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        resource_id=resource_id,
        response_status=response_status,
        now=now,
        key_id=uuid4(),
    )


__all__ = ["ClaimResult", "IdempotencyRecord", "check_existing", "claim_or_replay"]
