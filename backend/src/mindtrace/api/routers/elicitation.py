"""``/v1/elicitation/*`` (``docs/api/08`` s7, M8).

Fixed-order Twin Interview only - no Active Elicitation/EIG (deferred past
M10, see ``engines.elicitation.select_fixed``'s module docstring).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status

from mindtrace.api.deps import get_current_user_id, get_key_provider, now
from mindtrace.api.schemas.elicitation import (
    CredibleIntervalOut,
    ElicitationAnswer,
    ElicitationSession,
    ElicitationStep,
    FinalizeResultOut,
    InterviewItemKindOut,
    InterviewItemOut,
    InterviewProgressOut,
    TraitKindOut,
    TraitReportOut,
)
from mindtrace.db.crypto import KeyProvider
from mindtrace.domain.enums import InterviewItemType
from mindtrace.domain.ids import InterviewItemId, InterviewSessionId, UserId
from mindtrace.domain.interview import DispositionItem, PairwiseItem
from mindtrace.domain.traits import TraitReport
from mindtrace.services import elicitation_service
from mindtrace.services.elicitation_service import SessionState

router = APIRouter(prefix="/v1/elicitation", tags=["elicitation"])

_DISPOSITION_KIND_BY_TYPE: dict[InterviewItemType, InterviewItemKindOut] = {
    InterviewItemType.GAMBLE: "gamble",
    InterviewItemType.INTERTEMPORAL: "intertemporal",
    InterviewItemType.AMBIGUITY: "ambiguity",
    InterviewItemType.EFFORT: "effort",
}
_DISPOSITION_TRAIT_IDS = frozenset(
    {"risk_tolerance", "time_discount", "ambiguity_aversion", "effort_tolerance"}
)


@router.post("/sessions", response_model=ElicitationSession, status_code=status.HTTP_201_CREATED)
def create_session(
    user_id: UserId = Depends(get_current_user_id), request_time: datetime = Depends(now)
) -> ElicitationSession:
    """Start a new Twin Interview session."""
    state = elicitation_service.start_session(user_id, now=request_time)
    return _to_session_out(state)


@router.get("/sessions/{session_id}", response_model=ElicitationSession)
def get_session(
    session_id: UUID,
    user_id: UserId = Depends(get_current_user_id),
    key_provider: KeyProvider = Depends(get_key_provider),
) -> ElicitationSession:
    """Return one of the caller's own interview sessions."""
    state = elicitation_service.get_session_state(
        user_id, InterviewSessionId(session_id), key_provider=key_provider
    )
    return _to_session_out(state)


@router.post("/sessions/{session_id}/answers", response_model=ElicitationStep)
def submit_answer(
    session_id: UUID,
    body: ElicitationAnswer,
    user_id: UserId = Depends(get_current_user_id),
    key_provider: KeyProvider = Depends(get_key_provider),
    request_time: datetime = Depends(now),
) -> ElicitationStep:
    """Record one answer and return the updated session state."""
    state = elicitation_service.submit_answer(
        user_id,
        InterviewSessionId(session_id),
        item_id=InterviewItemId(body.item_id),
        choice=body.choice,
        latency_ms=body.latency_ms,
        key_provider=key_provider,
        now=request_time,
    )
    return ElicitationStep(
        accepted=True,
        next_item=_to_item_out(state.next_item),
        progress=_to_progress_out(state),
        trait_preview=[_to_trait_report_out(r) for r in state.trait_preview],
    )


@router.post("/sessions/{session_id}:finalize", response_model=FinalizeResultOut)
def finalize_session(
    session_id: UUID,
    user_id: UserId = Depends(get_current_user_id),
    key_provider: KeyProvider = Depends(get_key_provider),
    request_time: datetime = Depends(now),
) -> FinalizeResultOut:
    """Finalize a completed interview session into a new ``TwinVersion``."""
    result = elicitation_service.finalize(
        user_id, InterviewSessionId(session_id), key_provider=key_provider, now=request_time
    )
    return FinalizeResultOut(
        twin_id=result.twin_id,
        twin_version_id=result.twin_version.id,
        interview_noise=result.interview_noise,
    )


def _to_session_out(state: SessionState) -> ElicitationSession:
    return ElicitationSession(
        session_id=state.session.id,
        progress=_to_progress_out(state),
        next_item=_to_item_out(state.next_item),
    )


def _to_progress_out(state: SessionState) -> InterviewProgressOut:
    return InterviewProgressOut(answered=state.progress.answered, target=state.progress.target)


def _to_item_out(item: PairwiseItem | DispositionItem | None) -> InterviewItemOut | None:
    if item is None:
        return None
    if isinstance(item, PairwiseItem):
        return InterviewItemOut(
            item_id=str(item.id),
            kind="pairwise",
            prompt_a=item.prompt_a,
            prompt_b=item.prompt_b,
            prompt=None,
        )
    kind: InterviewItemKindOut = _DISPOSITION_KIND_BY_TYPE[item.type]
    return InterviewItemOut(
        item_id=str(item.id),
        kind=kind,
        prompt_a=item.prompt_a,
        prompt_b=item.prompt_b,
        prompt=None,
    )


def _to_trait_report_out(report: TraitReport) -> TraitReportOut:
    kind: TraitKindOut = (
        "disposition" if report.id in _DISPOSITION_TRAIT_IDS else "importance_weight"
    )
    source: Literal["declared", "inferred"] = (
        "inferred" if report.source == "inferred" else "declared"
    )
    return TraitReportOut(
        id=report.id,
        kind=kind,
        value=report.value,
        confidence=report.confidence,
        credible_interval=CredibleIntervalOut(
            low=report.credible_interval.low, high=report.credible_interval.high
        ),
        evidence_count=report.evidence_count,
        source=source,
        trend=None,
    )
