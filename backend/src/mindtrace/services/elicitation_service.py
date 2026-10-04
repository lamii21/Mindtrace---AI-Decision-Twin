"""The fixed-order Twin Interview use case (M8): sessions, answers, finalize.

Coordinates the pure engines (``engines.elicitation``, ``engines.preference``)
around persistence (``db.repositories.{twin_repository,interview_repository}``,
the existing ``PostgresEventStore``) - computes no Bradley-Terry/Beta
mathematics itself. Active Elicitation (adaptive EIG) is out of scope; item
selection is always the fixed order (``engines.elicitation.select_fixed``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import uuid4

from mindtrace.db.crypto import KeyProvider
from mindtrace.db.event_store import PostgresEventStore
from mindtrace.db.repositories import interview_repository, twin_repository
from mindtrace.db.repositories.evidence_repository import PostgresEvidenceStore
from mindtrace.db.session import user_scoped_session
from mindtrace.domain.enums import (
    BeliefType,
    ChoiceOption,
    EvidenceSourceKind,
    Polarity,
    ProvenanceSource,
    TwinVersionReason,
)
from mindtrace.domain.evidence import Evidence
from mindtrace.domain.factors import FactorTaxonomy, load_factor_taxonomy
from mindtrace.domain.ids import (
    EvidenceId,
    InterviewItemId,
    InterviewSessionId,
    TwinId,
    TwinVersionId,
    UserId,
)
from mindtrace.domain.interview import (
    DispositionItem,
    InterviewBank,
    InterviewSession,
    PairwiseItem,
    load_interview_bank,
)
from mindtrace.domain.traits import TraitModel, TraitReport, load_trait_model
from mindtrace.domain.twin import TwinVersion
from mindtrace.engines.elicitation.finalize import FINALIZE_VERSION, finalize_interview
from mindtrace.engines.elicitation.select_fixed import next_item_id
from mindtrace.engines.elicitation.session import InterviewProgress, is_complete, progress_for
from mindtrace.engines.preference.config import DEFAULT_PREFERENCE_CONFIG
from mindtrace.engines.preference.posterior import disposition_report, weight_report
from mindtrace.engines.preference.prior import initial_posterior
from mindtrace.engines.preference.projection import project_effective_weights
from mindtrace.events.projectors.preference import fold_elicitation_answer_events
from mindtrace.events.types import ElicitationAnsweredPayload
from mindtrace.services.errors import (
    InterviewNotCompleteError,
    InvalidInterviewItemError,
    ResourceNotFoundError,
    SessionAlreadyFinalizedError,
)

_TAXONOMY: FactorTaxonomy = load_factor_taxonomy()
_TRAIT_MODEL: TraitModel = load_trait_model(taxonomy=_TAXONOMY)
_BANK: InterviewBank = load_interview_bank(taxonomy=_TAXONOMY, trait_model=_TRAIT_MODEL)
_ALL_ITEM_IDS = frozenset(_BANK.item_ids)
_ITEMS_BY_ID: dict[InterviewItemId, PairwiseItem | DispositionItem] = {
    **{item.id: item for item in _BANK.pairwise},
    **{item.id: item for item in _BANK.disposition},
}


@dataclass(frozen=True)
class SessionState:
    """Everything a session's HTTP response needs, derived fresh from the event log each call."""

    session: InterviewSession
    progress: InterviewProgress
    next_item: PairwiseItem | DispositionItem | None
    trait_preview: tuple[TraitReport, ...]


@dataclass(frozen=True)
class FinalizeResult:
    """What ``POST .../:finalize`` reports."""

    twin_id: TwinId
    twin_version: TwinVersion
    interview_noise: float


def start_session(user_id: UserId, *, now: datetime) -> SessionState:
    """Begin a new interview session - always the first fixed-order item, no prior answers."""
    session = interview_repository.create_session(user_id, now=now)
    return _state_for(session, answers={})


def get_session_state(
    user_id: UserId, session_id: InterviewSessionId, *, key_provider: KeyProvider
) -> SessionState:
    """Current progress/next-item/trait-preview for an existing session.

    Raises:
        ResourceNotFoundError: the session does not exist / is not owned by
            ``user_id`` (RLS makes the two indistinguishable).
    """
    session = _get_owned_session(user_id, session_id)
    answers = _fold_answers(user_id, session_id, key_provider=key_provider)
    return _state_for(session, answers=answers)


def submit_answer(
    user_id: UserId,
    session_id: InterviewSessionId,
    *,
    item_id: InterviewItemId,
    choice: Literal["A", "B", "indifferent"],
    latency_ms: int | None,
    key_provider: KeyProvider,
    now: datetime,
) -> SessionState:
    """Append one ``elicitation_answered`` event and return the updated session state.

    A later answer for the same ``item_id`` is never a mutation - it is a
    new event; :func:`get_session_state`/finalisation use the latest one
    per item (M8 planning s4 "latest-answer-wins").

    Raises:
        ResourceNotFoundError: as :func:`get_session_state`.
        SessionAlreadyFinalizedError: the session already finalized.
        InvalidInterviewItemError: ``item_id`` is not in the current bank.
    """
    session = _get_owned_session(user_id, session_id)
    _ensure_not_finalized(session)
    if item_id not in _ALL_ITEM_IDS:
        msg = f"{item_id!r} is not a known interview item"
        raise InvalidInterviewItemError(msg)

    store = PostgresEventStore(key_provider=key_provider)
    store.append(
        user_id=user_id,
        payload=ElicitationAnsweredPayload(item_id=item_id, choice=choice, latency_ms=latency_ms),
        source=ProvenanceSource.DECLARED,
        now=now,
        correlation_id=session_id,
    )
    answers = _fold_answers(user_id, session_id, key_provider=key_provider)
    return _state_for(session, answers=answers)


def finalize(
    user_id: UserId, session_id: InterviewSessionId, *, key_provider: KeyProvider, now: datetime
) -> FinalizeResult:
    """Finalize a completed session into a new, immutable ``TwinVersion``.

    Raises:
        ResourceNotFoundError: as :func:`get_session_state`.
        SessionAlreadyFinalizedError: already finalized - never creates a
            second ``TwinVersion`` nor duplicates ``Evidence`` for the same
            session (M8 planning s14).
        InterviewNotCompleteError: not every fixed-order item has an answer
            yet.
    """
    session = _get_owned_session(user_id, session_id)
    _ensure_not_finalized(session)

    answered_events = fold_elicitation_answer_events(
        PostgresEventStore(key_provider=key_provider).read_stream(user_id), session_id=session_id
    )
    if not is_complete(_BANK, frozenset(answered_events)):
        msg = f"interview session {session_id} is not complete yet"
        raise InterviewNotCompleteError(msg)

    answers = {item_id: answered.choice for item_id, answered in answered_events.items()}
    prior = initial_posterior(_TRAIT_MODEL)
    posterior, interview_noise = finalize_interview(
        _BANK, _TAXONOMY, prior, answers, base_config=DEFAULT_PREFERENCE_CONFIG
    )
    effective = project_effective_weights(posterior, _TRAIT_MODEL)

    with user_scoped_session(user_id) as db_session:
        twin_model = twin_repository.get_or_create_twin(
            db_session, user_id=user_id, name="Primary", now=now
        )
        version_number = twin_repository.allocate_next_version(db_session, twin_model)
        twin_version = TwinVersion(
            id=TwinVersionId(uuid4()),
            user_id=user_id,
            twin_id=TwinId(twin_model.id),
            version=version_number,
            trait_snapshot=posterior,
            weights=effective.weights,
            dispositions=effective.dispositions,
            reason=TwinVersionReason.POST_ELICITATION,
            engine_version=posterior.engine_version,
            projection_version=effective.projection_version,
            factor_schema_version=_TAXONOMY.version,
            trait_schema_version=_TRAIT_MODEL.version,
            created_at=now,
        )
        twin_repository.create_twin_version(db_session, twin_version=twin_version)

        evidence_store = PostgresEvidenceStore(db_session, user_id=user_id)
        for answered in answered_events.values():
            evidence_store.record(
                Evidence(
                    id=EvidenceId(uuid4()),
                    user_id=user_id,
                    belief_type=BeliefType.PREFERENCE,
                    belief_id=twin_version.id,
                    source_kind=EvidenceSourceKind.ELICITATION_ANSWER,
                    source_id=answered.event_id,
                    weight=1.0,
                    polarity=Polarity.SUPPORT,
                    engine_version=FINALIZE_VERSION,
                    created_at=now,
                )
            )

        interview_repository.finalize_session(
            db_session,
            session_id=session_id,
            twin_id=TwinId(twin_model.id),
            resulting_twin_version_id=twin_version.id,
            interview_noise=interview_noise,
            now=now,
        )

    return FinalizeResult(
        twin_id=TwinId(twin_model.id), twin_version=twin_version, interview_noise=interview_noise
    )


def _get_owned_session(user_id: UserId, session_id: InterviewSessionId) -> InterviewSession:
    session = interview_repository.get_session(user_id, session_id)
    if session is None:
        msg = f"interview session {session_id} not found"
        raise ResourceNotFoundError(msg)
    return session


def _ensure_not_finalized(session: InterviewSession) -> None:
    if session.is_finalized:
        msg = f"interview session {session.id} is already finalized"
        raise SessionAlreadyFinalizedError(msg)


def _fold_answers(
    user_id: UserId, session_id: InterviewSessionId, *, key_provider: KeyProvider
) -> dict[InterviewItemId, ChoiceOption | None]:
    events = PostgresEventStore(key_provider=key_provider).read_stream(user_id)
    answered = fold_elicitation_answer_events(events, session_id=session_id)
    return {item_id: a.choice for item_id, a in answered.items()}


def _state_for(
    session: InterviewSession, *, answers: dict[InterviewItemId, ChoiceOption | None]
) -> SessionState:
    answered_ids = frozenset(answers)
    progress = progress_for(_BANK, answered_ids)
    next_id = next_item_id(_BANK, answered_ids)
    next_item = _ITEMS_BY_ID[next_id] if next_id is not None else None
    preview = _trait_preview(answers)
    return SessionState(
        session=session, progress=progress, next_item=next_item, trait_preview=preview
    )


def _trait_preview(answers: dict[InterviewItemId, ChoiceOption | None]) -> tuple[TraitReport, ...]:
    """A live, discarded-after-use preview of the posterior if finalized right now.

    Calls the same pure batch-update path :func:`finalize` uses
    (``engines.elicitation.finalize_interview``) with whatever has been
    answered so far - never incrementally, never persisted. Empty when
    nothing has been answered yet (the prior, with nothing to preview).
    """
    if not answers:
        return ()
    prior = initial_posterior(_TRAIT_MODEL)
    posterior, _noise = finalize_interview(
        _BANK, _TAXONOMY, prior, answers, base_config=DEFAULT_PREFERENCE_CONFIG
    )
    core_ids = _TRAIT_MODEL.core_weight_factor_ids
    weight_reports = (
        weight_report(posterior.weights, core_ids, factor_id, _TRAIT_MODEL, evidence_count=1)
        for factor_id in sorted(core_ids)
    )
    disposition_reports = (
        disposition_report(posterior.dispositions[disposition_id], _TRAIT_MODEL, evidence_count=1)
        for disposition_id in sorted(posterior.dispositions)
    )
    return tuple(weight_reports) + tuple(disposition_reports)


__all__ = [
    "FinalizeResult",
    "SessionState",
    "finalize",
    "get_session_state",
    "start_session",
    "submit_answer",
]
