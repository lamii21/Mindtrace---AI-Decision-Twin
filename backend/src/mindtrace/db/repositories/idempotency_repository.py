"""Persistence-backed idempotency (``docs/api/08`` s1).

``claim`` is the whole mechanism: it attempts an ``INSERT`` and lets the
table's own ``UNIQUE(user_id, route, idempotency_key)`` constraint
(``migrations/versions/0002_auth_and_idempotency.py``) do the concurrency
control - two concurrent requests racing on the same key can never both
"win"; PostgreSQL serialises them at the constraint, not in application
code (M6-API planning s9). The losing attempt's transaction is rolled back
and closed by :func:`~mindtrace.db.session.user_scoped_session` itself (it
never continues using a session after a failed flush); the follow-up read of
the winning row happens in a fresh transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from mindtrace.db.models.idempotency_key import IdempotencyKeyModel
from mindtrace.db.session import user_scoped_session
from mindtrace.domain.ids import UserId


@dataclass(frozen=True)
class IdempotencyRecord:
    """What a prior claim on this key looked like."""

    request_fingerprint: str
    resource_id: UUID
    response_status: int


@dataclass(frozen=True)
class ClaimResult:
    """The outcome of :func:`claim`.

    ``claimed=True``: this call won the race - the caller creates the
    resource. ``claimed=False``: a prior request already claimed this key;
    ``existing`` describes it, and the caller replays it instead of creating
    a second resource.
    """

    claimed: bool
    existing: IdempotencyRecord | None


def find_existing(*, user_id: UserId, route: str, idempotency_key: str) -> IdempotencyRecord | None:
    """Look up a prior claim without creating one - the sequential-retry fast path.

    Callers check this *before* doing any side-effecting work: if a claim
    already exists, nothing new should be created at all (``api/idempotency.py``'s
    "second call creates nothing new" guarantee). ``claim`` alone cannot give
    that - it needs a ``resource_id`` that only exists after the work runs.
    """
    with user_scoped_session(user_id) as session:
        row = session.execute(
            select(IdempotencyKeyModel).where(
                IdempotencyKeyModel.user_id == user_id,
                IdempotencyKeyModel.route == route,
                IdempotencyKeyModel.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return IdempotencyRecord(
            request_fingerprint=row.request_fingerprint,
            resource_id=row.resource_id,
            response_status=row.response_status,
        )


def claim(
    *,
    user_id: UserId,
    route: str,
    idempotency_key: str,
    request_fingerprint: str,
    resource_id: UUID,
    response_status: int,
    now: datetime,
    key_id: UUID,
) -> ClaimResult:
    """Attempt to claim ``idempotency_key`` for ``route`` for ``user_id``."""
    try:
        with user_scoped_session(user_id) as session:
            session.add(
                IdempotencyKeyModel(
                    id=key_id,
                    user_id=user_id,
                    route=route,
                    idempotency_key=idempotency_key,
                    request_fingerprint=request_fingerprint,
                    resource_id=resource_id,
                    response_status=response_status,
                    created_at=now,
                )
            )
            session.flush()
    except IntegrityError:
        pass
    else:
        return ClaimResult(claimed=True, existing=None)

    with user_scoped_session(user_id) as session:
        row = session.execute(
            select(IdempotencyKeyModel).where(
                IdempotencyKeyModel.user_id == user_id,
                IdempotencyKeyModel.route == route,
                IdempotencyKeyModel.idempotency_key == idempotency_key,
            )
        ).scalar_one()
        existing = IdempotencyRecord(
            request_fingerprint=row.request_fingerprint,
            resource_id=row.resource_id,
            response_status=row.response_status,
        )
    return ClaimResult(claimed=False, existing=existing)
