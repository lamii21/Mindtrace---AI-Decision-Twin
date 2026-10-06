"""``/v1/evidence``, ``/v1/beliefs/*:dispute`` (``docs/api/08`` s8, M9).

Evidence reads + belief disputes only - no Contradiction Engine (AG-10, a
system-detected-conflict review flow, out of scope), no Evaluation Engine
(``GET /v1/evaluation/*``, explicitly Phase 2+).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, status

from mindtrace.api.deps import get_current_user_id, get_key_provider, now
from mindtrace.api.schemas.evidence import (
    BeliefSummaryOut,
    BeliefTypeOut,
    DisputeAccepted,
    DisputeRequest,
    EvidenceChainOut,
    EvidenceEdgeOut,
    SourceKindOut,
)
from mindtrace.db.crypto import KeyProvider
from mindtrace.domain.enums import BeliefType, EvidenceSourceKind, Polarity
from mindtrace.domain.ids import InterviewItemId, UserId
from mindtrace.services import evidence_service
from mindtrace.services.evidence_service import EvidenceChainResult

router = APIRouter(tags=["evidence"])

_BELIEF_TYPE_OUT: dict[BeliefType, BeliefTypeOut] = {
    BeliefType.PREFERENCE: "preference",
    BeliefType.TRAIT: "trait",
    BeliefType.VALUE: "value",
    BeliefType.DECISION_FACTOR: "decision_factor",
    BeliefType.CONTRADICTION: "contradiction",
}
_SOURCE_KIND_OUT: dict[EvidenceSourceKind, SourceKindOut] = {
    EvidenceSourceKind.MEMORY: "memory",
    EvidenceSourceKind.DECISION: "decision",
    EvidenceSourceKind.ELICITATION_ANSWER: "elicitation_answer",
    EvidenceSourceKind.OUTCOME: "outcome",
}
_POLARITY_OUT: dict[Polarity, Literal["support", "contradict"]] = {
    Polarity.SUPPORT: "support",
    Polarity.CONTRADICT: "contradict",
}


@router.get("/v1/evidence/{belief_type}/{belief_id}", response_model=EvidenceChainOut)
def get_evidence_chain(
    belief_type: BeliefTypeOut,
    belief_id: UUID,
    user_id: UserId = Depends(get_current_user_id),
    key_provider: KeyProvider = Depends(get_key_provider),
) -> EvidenceChainOut:
    """Return the full provenance chain for one of the caller's own beliefs."""
    result = evidence_service.get_evidence_chain(
        user_id, BeliefType(belief_type), belief_id, key_provider=key_provider
    )
    return _to_chain_out(result)


@router.post(
    "/v1/beliefs/{belief_type}/{belief_id}:dispute",
    response_model=DisputeAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def dispute_belief(
    belief_type: BeliefTypeOut,
    belief_id: UUID,
    body: DisputeRequest,
    user_id: UserId = Depends(get_current_user_id),
    key_provider: KeyProvider = Depends(get_key_provider),
    request_time: datetime = Depends(now),
) -> DisputeAccepted:
    """Resolve a dispute into a new ``TwinVersion`` (never mutates the disputed one)."""
    result = evidence_service.dispute(
        user_id,
        BeliefType(belief_type),
        belief_id,
        item_id=InterviewItemId(body.item_id),
        choice=body.choice,
        reason=body.reason,
        key_provider=key_provider,
        now=request_time,
    )
    return DisputeAccepted(event_id=result.event_id, job_id=uuid4())


def _to_chain_out(result: EvidenceChainResult) -> EvidenceChainOut:
    return EvidenceChainOut(
        belief=BeliefSummaryOut(
            type=_BELIEF_TYPE_OUT[result.belief.belief_type],
            id=result.belief.belief_id,
            label=result.belief.label,
            value=result.belief.value,
            confidence=result.belief.confidence,
            source=result.belief.source,
        ),
        engine_version=result.engine_version,
        edges=[_to_edge_out(view) for view in result.edges],
    )


def _to_edge_out(view: evidence_service.EvidenceEdgeView) -> EvidenceEdgeOut:
    return EvidenceEdgeOut(
        source_kind=_SOURCE_KIND_OUT[view.evidence.source_kind],
        source_id=view.evidence.source_id,
        source_excerpt=view.source_excerpt,
        weight=view.evidence.weight,
        polarity=_POLARITY_OUT[view.evidence.polarity],
        engine_version=view.evidence.engine_version,
        created_at=view.evidence.created_at,
    )
