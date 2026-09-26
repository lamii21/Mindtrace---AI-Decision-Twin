"""Memory request/response DTOs (``docs/api/08`` s3). Field names/shapes are exact."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_FrozenExtraForbid = ConfigDict(extra="forbid")

MemoryKind = Literal["note", "experience", "decision_record", "preference_statement"]
MemoryTypeOut = Literal["episodic", "semantic", "preference", "decision"]
MemorySourceIn = Literal["declared", "observed"]
MemorySourceOut = Literal["declared", "observed", "inferred"]


class MemoryCreate(BaseModel):
    """``POST /v1/memories`` request body."""

    model_config = _FrozenExtraForbid

    kind: MemoryKind
    text: str = Field(min_length=1, max_length=8000)
    source: MemorySourceIn
    occurred_at: datetime | None = None
    structured: dict[str, object] | None = None


class MemoryAccepted(BaseModel):
    """``POST /v1/memories`` response body."""

    model_config = _FrozenExtraForbid

    memory_event_id: UUID
    projection: Literal["pending", "done"]
    memory_id: UUID | None = None


class BeliefRef(BaseModel):
    """A belief citing a memory as evidence - ``MemoryOut.supports``."""

    model_config = _FrozenExtraForbid

    belief_type: str
    belief_id: UUID


class MemoryOut(BaseModel):
    """``GET /v1/memories``/``GET /v1/memories/{id}`` response body."""

    model_config = _FrozenExtraForbid

    id: UUID
    type: MemoryTypeOut
    text: str
    source: MemorySourceOut
    confidence: float
    occurred_at: datetime | None
    created_at: datetime | None
    origin_event_seq: int
    supports: list[BeliefRef]
    superseded_by: UUID | None
    deleted_at: datetime | None


class BeliefImpact(BaseModel):
    """One belief a deletion would affect - ``DeletionPlan.affected_beliefs``."""

    model_config = _FrozenExtraForbid

    belief_type: str
    belief_id: UUID
    label: str
    change: Literal["recompute", "remove"]
    before: float | None
    after_estimate: float | None


class TraitDelta(BaseModel):
    """One trait a deletion would affect - ``DeletionPlan.affected_traits``."""

    model_config = _FrozenExtraForbid

    id: str
    kind: Literal["importance_weight", "disposition"]
    before: float
    after: float


class DeletionPlan(BaseModel):
    """``DELETE /v1/memories/{id}?dry_run=true`` response body."""

    model_config = _FrozenExtraForbid

    target_memory_ids: list[UUID]
    affected_beliefs: list[BeliefImpact]
    affected_traits: list[TraitDelta]
    invalidated_predictions: int
    twin_version_will_bump: bool
    reversible: Literal[False] = False


class ForgetRequest(BaseModel):
    """``POST /v1/memories:forget`` request body.

    Not implemented in M6 - see ``services/memory_service.py``'s module
    docstring.
    """

    model_config = _FrozenExtraForbid

    topic: str
    dry_run: bool = True


class JobAccepted(BaseModel):
    """A ``202`` response body.

    Used for an operation performed synchronously behind an async-shaped
    envelope (M6-API planning - no worker exists yet).
    """

    model_config = _FrozenExtraForbid

    job_id: UUID
