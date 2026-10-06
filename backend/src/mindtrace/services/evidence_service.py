"""Evidence chain reads + belief disputes (M9; ``docs/api/08`` s8).

Connects to the *existing* ``Evidence``/``EvidenceStore`` M2 defined and M7/M8
already write to - no second provenance system. A dispute is "answer one
interview item again, with more emphasis" (``engines.elicitation.dispute``,
approved M9 scope): it produces a new, immutable ``TwinVersion`` exactly like
``elicitation_service.finalize`` does, never mutates an old one, and writes
one more ``Evidence`` edge + one ``AuditLog`` row in the same transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from mindtrace.db.crypto import KeyProvider
from mindtrace.db.event_store import PostgresEventStore
from mindtrace.db.repositories import audit_repository, twin_repository
from mindtrace.db.repositories.decision_repository import get_decision
from mindtrace.db.repositories.evidence_repository import PostgresEvidenceStore, list_for_belief
from mindtrace.db.repositories.memory_repository import get_memory
from mindtrace.db.repositories.simulation_repository import get_simulation
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
    DecisionId,
    EvidenceId,
    InterviewItemId,
    MemoryId,
    SimulationId,
    TwinId,
    TwinVersionId,
    UserId,
)
from mindtrace.domain.interview import (
    DispositionItem,
    InterviewBank,
    PairwiseItem,
    load_interview_bank,
)
from mindtrace.domain.traits import TraitModel, load_trait_model
from mindtrace.domain.twin import TwinVersion
from mindtrace.engines.elicitation.dispute import DISPUTE_VERSION, apply_dispute
from mindtrace.engines.preference.config import DEFAULT_PREFERENCE_CONFIG
from mindtrace.engines.preference.projection import project_effective_weights
from mindtrace.events.types import ElicitationAnsweredPayload
from mindtrace.observability.audit import build_audit_log
from mindtrace.services.errors import (
    InvalidInterviewItemError,
    ResourceNotFoundError,
    StaleBeliefError,
    UnsupportedBeliefTypeError,
)

_TAXONOMY: FactorTaxonomy = load_factor_taxonomy()
_TRAIT_MODEL: TraitModel = load_trait_model(taxonomy=_TAXONOMY)
_BANK: InterviewBank = load_interview_bank(taxonomy=_TAXONOMY, trait_model=_TRAIT_MODEL)
_ITEMS_BY_ID: dict[InterviewItemId, PairwiseItem | DispositionItem] = {
    **{item.id: item for item in _BANK.pairwise},
    **{item.id: item for item in _BANK.disposition},
}

# Only these recompute through the existing M4 preference engine. The other
# three BeliefType values recompute through paths M9 does not wire up
# (decision_factor would need a second /simulate, not a dispute; value/
# contradiction have no producer at all yet) - refused rather than silently
# accepted (M9 planning - approved scope).
_DISPUTABLE_BELIEF_TYPES: frozenset[BeliefType] = frozenset(
    {BeliefType.PREFERENCE, BeliefType.TRAIT}
)


@dataclass(frozen=True)
class BeliefSummary:
    """``EvidenceChain.belief`` - what the belief currently says, where it is resolvable."""

    belief_type: BeliefType
    belief_id: UUID
    label: str
    value: float | None
    confidence: float | None
    source: Literal["declared", "inferred"]


@dataclass(frozen=True)
class EvidenceEdgeView:
    """One ``Evidence`` edge plus its decrypted, ownership-checked excerpt."""

    evidence: Evidence
    source_excerpt: str


@dataclass(frozen=True)
class EvidenceChainResult:
    """``GET /v1/evidence/{type}/{id}`` response body, pre-DTO-shaping."""

    belief: BeliefSummary
    engine_version: str
    edges: tuple[EvidenceEdgeView, ...]


@dataclass(frozen=True)
class DisputeResult:
    """``POST /v1/beliefs/{type}/{id}:dispute`` response body, pre-DTO-shaping."""

    event_id: UUID
    twin_version: TwinVersion


def get_evidence_chain(
    user_id: UserId, belief_type: BeliefType, belief_id: UUID, *, key_provider: KeyProvider
) -> EvidenceChainResult:
    """The full provenance chain for one belief - "why do you believe this?".

    Raises:
        ResourceNotFoundError: no ``Evidence`` names this belief (it does not
            exist, is not ``user_id``'s, or no producer has derived it yet).
    """
    edges = list_for_belief(user_id, belief_type, belief_id)
    if not edges:
        msg = f"no evidence for belief {belief_type.value}/{belief_id}"
        raise ResourceNotFoundError(msg)

    belief = _summarize_belief(user_id, belief_type, belief_id, key_provider=key_provider)
    views = tuple(
        EvidenceEdgeView(
            evidence=edge, source_excerpt=_source_excerpt(user_id, edge, key_provider=key_provider)
        )
        for edge in edges
    )
    return EvidenceChainResult(belief=belief, engine_version=edges[0].engine_version, edges=views)


def dispute(
    user_id: UserId,
    belief_type: BeliefType,
    belief_id: UUID,
    *,
    item_id: InterviewItemId,
    choice: Literal["A", "B", "indifferent"],
    reason: str,
    key_provider: KeyProvider,
    now: datetime,
) -> DisputeResult:
    """Resolve a dispute into a new ``TwinVersion`` - never mutates ``belief_id``'s own snapshot.

    Raises:
        UnsupportedBeliefTypeError: ``belief_type`` is not ``preference``/``trait``.
        InvalidInterviewItemError: ``item_id`` is not in the current bank.
        StaleBeliefError: ``belief_id`` is not the caller's *current*
            ``TwinVersion`` - disputing history is refused outright.
    """
    if belief_type not in _DISPUTABLE_BELIEF_TYPES:
        msg = f"belief_type={belief_type.value!r} cannot be disputed yet"
        raise UnsupportedBeliefTypeError(msg)
    if item_id not in _ITEMS_BY_ID:
        msg = f"{item_id!r} is not a known interview item"
        raise InvalidInterviewItemError(msg)

    latest = twin_repository.get_latest_twin_version(user_id)
    if latest is None or UUID(str(latest.id)) != belief_id:
        msg = f"belief_id {belief_id} is not the current twin version"
        raise StaleBeliefError(msg)

    item = _ITEMS_BY_ID[item_id]
    choice_enum = ChoiceOption(choice) if choice != "indifferent" else None

    store = PostgresEventStore(key_provider=key_provider)
    event = store.append(
        user_id=user_id,
        payload=ElicitationAnsweredPayload(item_id=item_id, choice=choice, dispute_reason=reason),
        source=ProvenanceSource.DECLARED,
        now=now,
        correlation_id=None,
    )

    posterior = apply_dispute(
        item,
        choice_enum,
        latest.trait_snapshot,
        taxonomy=_TAXONOMY,
        config=DEFAULT_PREFERENCE_CONFIG,
    )
    effective = project_effective_weights(posterior, _TRAIT_MODEL)

    with user_scoped_session(user_id) as session:
        twin_model = twin_repository.get_or_create_twin(
            session, user_id=user_id, name="Primary", now=now
        )
        version_number = twin_repository.allocate_next_version(session, twin_model)
        new_version = TwinVersion(
            id=TwinVersionId(uuid4()),
            user_id=user_id,
            twin_id=TwinId(twin_model.id),
            version=version_number,
            trait_snapshot=posterior,
            weights=effective.weights,
            dispositions=effective.dispositions,
            reason=TwinVersionReason.MANUAL,
            engine_version=posterior.engine_version,
            projection_version=effective.projection_version,
            factor_schema_version=_TAXONOMY.version,
            trait_schema_version=_TRAIT_MODEL.version,
            created_at=now,
        )
        twin_repository.create_twin_version(session, twin_version=new_version)

        evidence_store = PostgresEvidenceStore(session, user_id=user_id)
        evidence_store.record(
            Evidence(
                id=EvidenceId(uuid4()),
                user_id=user_id,
                belief_type=belief_type,
                belief_id=UUID(str(new_version.id)),
                source_kind=EvidenceSourceKind.ELICITATION_ANSWER,
                source_id=UUID(str(event.id)),
                weight=1.0,
                polarity=Polarity.SUPPORT,
                engine_version=posterior.engine_version,
                created_at=now,
            )
        )

        audit_repository.append_audit(
            session,
            log=build_audit_log(
                user_id=user_id,
                actor=f"user:{user_id}",
                action="belief.disputed",
                target_type="twin_version",
                target_id=UUID(str(new_version.id)),
                engine_version=DISPUTE_VERSION,
                payload={
                    "previous_twin_version_id": str(latest.id),
                    "belief_type": belief_type.value,
                    "item_id": str(item_id),
                    "choice": choice,
                    "reason_present": bool(reason),
                },
                at=now,
            ),
        )

    return DisputeResult(event_id=UUID(str(event.id)), twin_version=new_version)


def _summarize_belief(
    user_id: UserId, belief_type: BeliefType, belief_id: UUID, *, key_provider: KeyProvider
) -> BeliefSummary:
    if belief_type in _DISPUTABLE_BELIEF_TYPES:
        twin_version = twin_repository.get_twin_version(user_id, TwinVersionId(belief_id))
        if twin_version is None:  # pragma: no cover - unreachable via get_evidence_chain's own
            # existence check (an Evidence edge naming this belief_id already had to exist to
            # get here); kept as a defensive guard against a future caller of this function.
            msg = f"no evidence for belief {belief_type.value}/{belief_id}"
            raise ResourceNotFoundError(msg)
        return BeliefSummary(
            belief_type=belief_type,
            belief_id=belief_id,
            label=f"TwinVersion v{twin_version.version}",
            value=None,
            confidence=None,
            source="inferred",
        )

    # belief_type == DECISION_FACTOR: belief_id is a Simulation id (decision_service.py).
    result = get_simulation(user_id, SimulationId(belief_id))
    if result is None:  # pragma: no cover - same reasoning as the branch above
        msg = f"no evidence for belief {belief_type.value}/{belief_id}"
        raise ResourceNotFoundError(msg)
    simulation, _prediction = result
    base = simulation.twin_configs[0]
    return BeliefSummary(
        belief_type=belief_type,
        belief_id=belief_id,
        label=f"decision_factor for decision {simulation.decision_id}",
        value=base.decision.score,
        confidence=simulation.model_confidence.value,
        source="inferred",
    )


def _source_excerpt(user_id: UserId, evidence: Evidence, *, key_provider: KeyProvider) -> str:
    """A short, decrypted, ownership-checked excerpt of what ``evidence`` cites."""
    if evidence.source_kind is EvidenceSourceKind.MEMORY:
        return _memory_excerpt(user_id, evidence.source_id, key_provider=key_provider)
    if evidence.source_kind is EvidenceSourceKind.DECISION:
        return _decision_excerpt(user_id, evidence.source_id, key_provider=key_provider)
    if evidence.source_kind is EvidenceSourceKind.ELICITATION_ANSWER:
        return _elicitation_answer_excerpt(user_id, evidence.source_id, key_provider=key_provider)
    return "(outcome)"  # pragma: no cover - EvidenceSourceKind.OUTCOME has no producer yet (M9)


def _memory_excerpt(user_id: UserId, source_id: UUID, *, key_provider: KeyProvider) -> str:
    found = get_memory(user_id, MemoryId(source_id), key_provider=key_provider)
    if found is None:  # pragma: no cover - the memory could be deleted after the fact
        return "(memory no longer available)"
    memory, _created_at = found
    return memory.content[:200]


def _decision_excerpt(user_id: UserId, source_id: UUID, *, key_provider: KeyProvider) -> str:
    decision = get_decision(user_id, DecisionId(source_id), key_provider=key_provider)
    if decision is None:  # pragma: no cover - defensive, same reasoning as above
        return "(decision no longer available)"
    return f"decision: {decision.title}"


def _elicitation_answer_excerpt(
    user_id: UserId, source_id: UUID, *, key_provider: KeyProvider
) -> str:
    answer = _find_answer_event(user_id, source_id, key_provider=key_provider)
    if answer is None:  # pragma: no cover - defensive
        return "(interview answer no longer available)"
    item_id, choice = answer
    return f"interview item {item_id}: chose {choice}"


def _find_answer_event(
    user_id: UserId, event_id: UUID, *, key_provider: KeyProvider
) -> tuple[str, str] | None:
    store = PostgresEventStore(key_provider=key_provider)
    for event in store.read_stream(user_id):
        if event.id == event_id:
            payload = ElicitationAnsweredPayload.model_validate(event.payload)
            return str(payload.item_id), payload.choice
    return None  # pragma: no cover - defensive; the event was just appended in this flow


__all__ = [
    "BeliefSummary",
    "DisputeResult",
    "EvidenceChainResult",
    "EvidenceEdgeView",
    "dispute",
    "get_evidence_chain",
]
