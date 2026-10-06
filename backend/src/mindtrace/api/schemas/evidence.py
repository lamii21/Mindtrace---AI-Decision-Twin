"""Evidence/dispute request-response DTOs (``docs/api/08`` s8, M9).

``DisputeRequest`` deviates from the literal doc contract
(``{reason, corrected_value}``): M9 planning approved ``{reason, item_id,
choice}`` instead, since no belief in this system is ever addressable at
single-factor granularity and converting a bare ``corrected_value: float``
into a Bradley-Terry/Beta observation has no existing formula to reuse
(would be new mathematics - explicitly out of scope). A dispute instead
replays one *existing* interview item with extra weight, reusing
``engines.elicitation.dispute`` exactly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_FrozenExtraForbid = ConfigDict(extra="forbid")

BeliefTypeOut = Literal["preference", "trait", "value", "decision_factor", "contradiction"]
SourceKindOut = Literal["memory", "decision", "elicitation_answer", "outcome"]


class BeliefSummaryOut(BaseModel):
    """``EvidenceChain.belief`` - what the belief currently says."""

    model_config = _FrozenExtraForbid

    type: BeliefTypeOut
    id: UUID
    label: str
    value: float | None
    confidence: float | None
    source: Literal["declared", "inferred"]


class EvidenceEdgeOut(BaseModel):
    """One provenance edge in an ``EvidenceChain``."""

    model_config = _FrozenExtraForbid

    source_kind: SourceKindOut
    source_id: UUID
    source_excerpt: str
    weight: float
    polarity: Literal["support", "contradict"]
    engine_version: str
    created_at: datetime


class EvidenceChainOut(BaseModel):
    """``GET /v1/evidence/{belief_type}/{belief_id}`` response body."""

    model_config = _FrozenExtraForbid

    belief: BeliefSummaryOut
    engine_version: str
    edges: list[EvidenceEdgeOut]


class DisputeRequest(BaseModel):
    """``POST /v1/beliefs/{belief_type}/{belief_id}:dispute`` request body (M9 planning s4)."""

    model_config = _FrozenExtraForbid

    reason: str = Field(min_length=1, max_length=2000)
    item_id: str
    choice: Literal["A", "B", "indifferent"]


class DisputeAccepted(BaseModel):
    """``POST /v1/beliefs/{belief_type}/{belief_id}:dispute`` response body."""

    model_config = _FrozenExtraForbid

    event_id: UUID
    job_id: UUID
