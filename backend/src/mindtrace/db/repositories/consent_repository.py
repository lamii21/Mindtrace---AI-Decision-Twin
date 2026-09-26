"""Persistence for AG-1's ``ConsentRecord``. Append-only - no update method exists here.

Every field is plaintext (M6-Persistence planning s3): the consent gate
itself needs to run equality queries (``WHERE user_id=? AND scope=?``), so
none of ``scope``/``granted``/``policy_version`` are prose ADR-008's
enumerated column list ever names.
"""

from __future__ import annotations

from sqlalchemy import select

from mindtrace.db.models.consent_record import ConsentRecordModel
from mindtrace.db.session import user_scoped_session
from mindtrace.domain.consent import ConsentRecord
from mindtrace.domain.enums import ConsentScope
from mindtrace.domain.ids import ConsentRecordId, UserId


def append_consent(record: ConsentRecord) -> None:
    """Append one consent statement. Never updates a prior row for the same scope."""
    with user_scoped_session(record.user_id) as session:
        session.add(
            ConsentRecordModel(
                id=record.id,
                user_id=record.user_id,
                scope=record.scope.value,
                granted=record.granted,
                policy_version=record.policy_version,
                at=record.at,
            )
        )


def list_consent(user_id: UserId) -> tuple[ConsentRecord, ...]:
    """The full, ordered consent history for ``user_id`` - oldest first."""
    with user_scoped_session(user_id) as session:
        rows = (
            session.execute(
                select(ConsentRecordModel)
                .where(ConsentRecordModel.user_id == user_id)
                .order_by(ConsentRecordModel.at)
            )
            .scalars()
            .all()
        )
        return tuple(
            ConsentRecord(
                id=ConsentRecordId(row.id),
                user_id=user_id,
                scope=ConsentScope(row.scope),
                granted=row.granted,
                policy_version=row.policy_version,
                at=row.at,
            )
            for row in rows
        )
