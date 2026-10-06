"""``AuditLog`` - the append-only accountability ledger (``docs/architecture/02`` cross-cutting).

Tier A (never ``UPDATE``, never ``DELETE``), like ``MemoryEvent``/
``ConsentRecord``. Proves *what* produced a belief/derivation without storing
the prose that drove it: ``payload_hash`` is a sha256 of the canonicalised
input facts, never the free text itself (M9 planning - a dispute's ``reason``
lives in the encrypted ``elicitation_answered`` event payload, not here).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from mindtrace.domain.ids import AuditLogId, UserId

_FrozenModel = ConfigDict(frozen=True, extra="forbid")


class AuditLog(BaseModel):
    """One accountability record: who/what did ``action`` to ``target``, and why it is trustworthy.

    ``actor`` follows the documented convention ``"user:<id>"`` /
    ``"system:<engine>"`` / ``"worker:<task>"`` - a formatted string, not a
    closed enum, since the set of actors grows with every new engine/worker
    (``docs/architecture/02-domain-model.md`` cross-cutting section).
    ``action`` is similarly open-ended (``"belief.derived"``,
    ``"memory.deleted"``, ``"belief.disputed"``, ...).
    """

    model_config = _FrozenModel

    id: AuditLogId
    user_id: UserId
    actor: str = Field(min_length=1)
    action: str = Field(min_length=1)
    target_type: str = Field(min_length=1)
    target_id: UUID
    engine_version: str | None
    payload_hash: str = Field(min_length=1)
    at: datetime
