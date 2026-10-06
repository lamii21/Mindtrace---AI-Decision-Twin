"""Building an :class:`~mindtrace.domain.audit.AuditLog` row (M9).

Pure: computes ``payload_hash`` from the caller's already-assembled input
facts and returns a frozen domain object - no DB write happens here (that is
``db.repositories.audit_repository.append_audit``'s job, called from
``services/`` in the same transaction as whatever this audit row records).
``payload`` must never contain free-text prose (a dispute's ``reason``, a
memory's content, ...) - only ids, enums, and small scalars - so hashing it
can never leak anything sensitive even though the hash itself is readable by
anyone who can query ``audit_log`` (``docs/architecture/02-domain-model.md``
cross-cutting section: "lets you prove *what* produced a belief without
storing the prose").
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import datetime
from uuid import UUID, uuid4

from mindtrace.domain.audit import AuditLog
from mindtrace.domain.ids import AuditLogId, UserId


def build_audit_log(
    *,
    user_id: UserId,
    actor: str,
    action: str,
    target_type: str,
    target_id: UUID,
    engine_version: str | None,
    payload: Mapping[str, object],
    at: datetime,
    id_factory: Callable[[], UUID] = uuid4,
) -> AuditLog:
    """Build one :class:`AuditLog` row; ``payload_hash`` is a sha256 of ``payload``'s JSON."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return AuditLog(
        id=AuditLogId(id_factory()),
        user_id=user_id,
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        engine_version=engine_version,
        payload_hash=payload_hash,
        at=at,
    )


__all__ = ["build_audit_log"]
