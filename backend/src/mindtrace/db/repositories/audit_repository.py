"""Persistence for ``AuditLog`` (M9). Append-only - no update method exists here.

Takes an already-open ``Session`` rather than opening its own, like
``evidence_repository.PostgresEvidenceStore``: an audit row must commit in
the same atomic transaction as the derivation it records (e.g. the new
``TwinVersion`` a dispute produces), never as an afterthought that could
survive a rollback the derivation itself didn't.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from mindtrace.db.models.audit_log import AuditLogModel
from mindtrace.db.session import user_scoped_session
from mindtrace.domain.audit import AuditLog
from mindtrace.domain.ids import AuditLogId, UserId


def append_audit(session: Session, *, log: AuditLog) -> None:
    """Append one immutable audit row, within the caller-owned ``session``."""
    session.add(
        AuditLogModel(
            id=log.id,
            user_id=log.user_id,
            actor=log.actor,
            action=log.action,
            target_type=log.target_type,
            target_id=log.target_id,
            engine_version=log.engine_version,
            payload_hash=log.payload_hash,
            at=log.at,
        )
    )


def list_for_target(user_id: UserId, *, target_type: str, target_id: UUID) -> tuple[AuditLog, ...]:
    """Every audit row for one target, oldest first - for tests/future audit reads."""
    with user_scoped_session(user_id) as session:
        rows = (
            session.execute(
                select(AuditLogModel)
                .where(
                    AuditLogModel.user_id == user_id,
                    AuditLogModel.target_type == target_type,
                    AuditLogModel.target_id == target_id,
                )
                .order_by(AuditLogModel.at)
            )
            .scalars()
            .all()
        )
        return tuple(
            AuditLog(
                id=AuditLogId(row.id),
                user_id=UserId(row.user_id),
                actor=row.actor,
                action=row.action,
                target_type=row.target_type,
                target_id=row.target_id,
                engine_version=row.engine_version,
                payload_hash=row.payload_hash,
                at=row.at,
            )
            for row in rows
        )
