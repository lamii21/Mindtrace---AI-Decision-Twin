"""Memory ingestion, retrieval, and explicit-id deletion (M6-API).

**Ingestion stays synchronous in M6** (``docs/api/08`` s1 itself documents
this precedent: "Projection after `POST /memories` is synchronous in
milestone M2, async (202) from M5" - M5 in this repository's actual build
order became the LLM boundary milestone, not an API+worker milestone, so no
async infrastructure exists yet; M6 continues M2's synchronous behaviour
rather than fabricating a queue). The event is the source of truth:
``PostgresEventStore.append`` is the commit point, and the projection
(``events.projectors.memory.fold_memory_events`` - unmodified) is rebuilt
from the *full* stream immediately after, then persisted via
``memory_repository.upsert_memory``. A crash between those two steps loses
nothing durable - the next read of this memory (or a future re-derivation
job) folds the same events to the same result; the projection step is
idempotent by construction, never a second source of truth.

``POST /v1/memories:forget`` (topic-based deletion) is **not implemented** in
M6: ``domain.memory``'s own module docstring already states that topic-based
deletion needs semantic matching over memory content, which needs embeddings
that do not exist yet ("M5+", never actually built). Faking a substring
match would misrepresent what "topic" matching is meant to do. Explicit-id
deletion (``DELETE /v1/memories/{id}``) is fully implemented - it is exactly
what M2 already proved out.

**M9** wires the *real* ``PostgresEvidenceStore`` into deletion preview/apply
in place of the throwaway ``InMemoryEvidenceStore`` M6 used (nothing yet
existed to write real evidence against a memory at the time) - and derives
``DeletionPlanFacts``/``invalidated_predictions`` from what that store
actually reports, rather than the router hard-coding empty values (M9
planning: a real, previously-silent gap - no current producer writes
``Evidence(source_kind=memory)`` either, so a real plan's impact is
honestly empty until one does; the wiring itself is what M9 proves works).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from mindtrace.db.crypto import KeyProvider
from mindtrace.db.event_store import PostgresEventStore
from mindtrace.db.repositories import audit_repository, memory_repository
from mindtrace.db.repositories.evidence_repository import PostgresEvidenceStore
from mindtrace.db.repositories.simulation_repository import get_simulation
from mindtrace.db.session import user_scoped_session
from mindtrace.domain.enums import BeliefType, MemoryType, ProvenanceSource
from mindtrace.domain.errors import DomainError
from mindtrace.domain.ids import MemoryId, SimulationId, UserId
from mindtrace.domain.memory import Memory
from mindtrace.events.deletion_plan import DeletionPlanFacts, build_deletion_plan_facts
from mindtrace.events.projectors.memory import MemoryProjectionState, fold_memory_events
from mindtrace.events.rederive import DeletionImpact, apply_deletion, preview_deletion
from mindtrace.events.types import IngestedPayload
from mindtrace.observability.audit import build_audit_log
from mindtrace.services.errors import MemoryAlreadyDeletedError, ResourceNotFoundError


@dataclass(frozen=True)
class DeletionPlanResult:
    """Everything ``DELETE /v1/memories/{id}``'s ``DeletionPlan`` response needs (M9)."""

    impact: DeletionImpact
    facts: DeletionPlanFacts
    invalidated_predictions: int


# API `kind` (input classification) -> projected `MemoryType` (AG-3's own
# vocabulary). Not documented as an explicit table anywhere - a direct,
# defensible 1:1 reading of the two vocabularies' evident intent
# (M6-API planning).
_KIND_TO_MEMORY_TYPE: dict[str, MemoryType] = {
    "note": MemoryType.SEMANTIC,
    "experience": MemoryType.EPISODIC,
    "decision_record": MemoryType.DECISION,
    "preference_statement": MemoryType.PREFERENCE,
}


def ingest(
    *,
    user_id: UserId,
    kind: str,
    text: str,
    source: ProvenanceSource,
    key_provider: KeyProvider,
    now: datetime,
) -> tuple[Memory, datetime]:
    """Append an ``ingested`` event and synchronously rebuild+persist the projection.

    Returns the newly-current :class:`~mindtrace.domain.memory.Memory` and
    its origin event's ``created_at`` - its ``id`` equals the originating
    event's id (M2's own identity rule).
    """
    store = PostgresEventStore(key_provider=key_provider)
    appended = store.append(
        user_id=user_id,
        payload=IngestedPayload(content=text, memory_type=_KIND_TO_MEMORY_TYPE[kind]),
        source=source,
        now=now,
    )
    state = _current_state(user_id=user_id, key_provider=key_provider)
    for memory in state.memories.values():
        memory_repository.upsert_memory(memory=memory, key_provider=key_provider)
    result = memory_repository.get_memory(user_id, MemoryId(appended.id), key_provider=key_provider)
    assert result is not None  # just persisted above
    return result


def get(
    user_id: UserId, memory_id: MemoryId, *, key_provider: KeyProvider
) -> tuple[Memory, datetime]:
    """Return one memory and its origin event's ``created_at``.

    Raises:
        ResourceNotFoundError: it does not exist, or is not owned by
            ``user_id`` (RLS makes the two indistinguishable - by design).
    """
    result = memory_repository.get_memory(user_id, memory_id, key_provider=key_provider)
    if result is None:
        msg = f"memory {memory_id} not found"
        raise ResourceNotFoundError(msg)
    return result


def list_memories(
    *,
    user_id: UserId,
    key_provider: KeyProvider,
    type_: MemoryType | None = None,
    source: ProvenanceSource | None = None,
) -> tuple[tuple[Memory, datetime], ...]:
    """Every current-or-not memory for ``user_id`` matching the given filters."""
    return memory_repository.list_memories(
        user_id, key_provider=key_provider, type_=type_, source=source
    )


def preview_delete(
    *, user_id: UserId, memory_ids: tuple[MemoryId, ...], key_provider: KeyProvider
) -> DeletionPlanResult:
    """Dry-run: compute what deleting ``memory_ids`` would affect, changing nothing.

    Raises:
        ResourceNotFoundError: a memory id is unknown to ``user_id`` - either
            it never existed or belongs to someone else. ``preview_deletion``
            (M2, unmodified) raises ``KeyError`` for that case; RLS already
            makes "doesn't exist" and "not yours" indistinguishable by
            scoping ``state`` to ``user_id``, so both collapse to 404 here.
        MemoryAlreadyDeletedError: a named memory is already tombstoned.
    """
    state = _current_state(user_id=user_id, key_provider=key_provider)
    with user_scoped_session(user_id) as session:
        evidence_store = PostgresEvidenceStore(session, user_id=user_id)
        try:
            impact = preview_deletion(state, memory_ids, evidence_store=evidence_store)
        except KeyError as exc:
            msg = f"memory {exc.args[0]} not found"
            raise ResourceNotFoundError(msg) from exc
        except DomainError as exc:
            raise MemoryAlreadyDeletedError(str(exc)) from exc
    return _build_plan_result(impact, user_id=user_id)


def apply_delete(
    *, user_id: UserId, memory_ids: tuple[MemoryId, ...], key_provider: KeyProvider, now: datetime
) -> tuple[DeletionPlanResult, UUID]:
    """Apply the deletion: append a ``deleted`` event, re-derive, persist.

    Returns ``(plan, job_id)`` - ``job_id`` is a fresh id matching the
    documented ``202 {job_id}`` response shape; the work itself already
    completed synchronously by the time this returns (see module docstring).

    Raises:
        ResourceNotFoundError: see :func:`preview_delete` - same translation
            of the underlying ``KeyError`` applies here.
        MemoryAlreadyDeletedError: see :func:`preview_delete`.
    """
    store = PostgresEventStore(key_provider=key_provider)
    state = _current_state(user_id=user_id, key_provider=key_provider)
    with user_scoped_session(user_id) as session:
        evidence_store = PostgresEvidenceStore(session, user_id=user_id)
        try:
            impact, new_state = apply_deletion(
                store,
                state,
                memory_ids,
                evidence_store=evidence_store,
                source=ProvenanceSource.DECLARED,
                now=now,
            )
        except KeyError as exc:
            msg = f"memory {exc.args[0]} not found"
            raise ResourceNotFoundError(msg) from exc
        except DomainError as exc:
            raise MemoryAlreadyDeletedError(str(exc)) from exc
    for memory in new_state.memories.values():
        memory_repository.upsert_memory(memory=memory, key_provider=key_provider)
    plan = _build_plan_result(impact, user_id=user_id)
    _record_deletion_audit(user_id=user_id, plan=plan, now=now)
    return plan, uuid4()


def _record_deletion_audit(*, user_id: UserId, plan: DeletionPlanResult, now: datetime) -> None:
    """One ``AuditLog`` row per applied deletion - never the memory content itself."""
    with user_scoped_session(user_id) as session:
        for memory_id in plan.impact.memory_ids:
            audit_repository.append_audit(
                session,
                log=build_audit_log(
                    user_id=user_id,
                    actor=f"user:{user_id}",
                    action="memory.deleted",
                    target_type="memory",
                    target_id=UUID(str(memory_id)),
                    engine_version=None,
                    payload={
                        "affected_belief_count": len(plan.facts.affected_beliefs),
                        "twin_version_will_bump": plan.facts.twin_version_will_bump,
                    },
                    at=now,
                ),
            )


def _build_plan_result(impact: DeletionImpact, *, user_id: UserId) -> DeletionPlanResult:
    facts = build_deletion_plan_facts(impact)
    invalidated_predictions = sum(
        1
        for fact in facts.affected_beliefs
        if fact.belief_type is BeliefType.DECISION_FACTOR
        and get_simulation(user_id, SimulationId(fact.belief_id)) is not None
    )
    return DeletionPlanResult(
        impact=impact, facts=facts, invalidated_predictions=invalidated_predictions
    )


def _current_state(*, user_id: UserId, key_provider: KeyProvider) -> MemoryProjectionState:
    store = PostgresEventStore(key_provider=key_provider)
    return fold_memory_events(user_id, store.read_stream(user_id))
