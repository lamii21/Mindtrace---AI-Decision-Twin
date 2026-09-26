"""Consent records (``docs/architecture/02-domain-model.md`` AG-1).

Append-only: a change of mind is a new row, never an update to an existing
one (ADR-008 item 8). The *current* state of a scope is derived by whoever
reads the stream ("the latest row for the relevant scope") - this module
defines only the row shape, not that read, since nothing in this milestone
needs it yet (no inference/LLM-call gating exists before the engines are
wired to the API).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from mindtrace.domain.enums import ConsentScope
from mindtrace.domain.ids import ConsentRecordId, UserId

_FrozenModel = ConfigDict(frozen=True, extra="forbid")


class ConsentRecord(BaseModel):
    """One immutable statement of consent (or its withdrawal) for one scope."""

    model_config = _FrozenModel

    id: ConsentRecordId
    user_id: UserId
    scope: ConsentScope
    granted: bool
    policy_version: str
    at: datetime
