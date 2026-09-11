"""Small, human-readable fixtures for the M2 memory/evidence/provenance layer.

Every builder is deterministic (fixed user, fixed clock, sequential ids) so a
test - or a future milestone importing these - gets the exact same values
every time. See ``docs/11-roadmap-milestones.md`` M2 s17: these are meant to
be reused by M3+ (MCDA, preference learning, confidence, provenance UI,
deletion tests), not just this milestone's own tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import count
from uuid import UUID, uuid4

from mindtrace.domain.enums import (
    BeliefType,
    EvidenceSourceKind,
    MemoryType,
    Polarity,
    ProvenanceSource,
)
from mindtrace.domain.evidence import Evidence
from mindtrace.domain.ids import EvidenceId, MemoryId, UserId
from mindtrace.domain.memory import Memory
from mindtrace.events.evidence_store import InMemoryEvidenceStore
from mindtrace.events.in_memory_store import InMemoryEventStore
from mindtrace.events.projectors.memory import (
    MEMORY_PROJECTOR_VERSION,
    MemoryProjectionState,
    fold_memory_events,
)
from mindtrace.events.types import CorrectedPayload, DeletedPayload, Event, IngestedPayload

FIXED_USER = UserId(UUID("00000000-0000-0000-0000-000000000001"))
OTHER_USER = UserId(UUID("00000000-0000-0000-0000-000000000002"))
FIXED_NOW = datetime(2026, 9, 12, 12, 0, 0, tzinfo=UTC)


def deterministic_store() -> InMemoryEventStore:
    """An :class:`InMemoryEventStore` whose event ids are sequential, not random."""
    counter = count(1)
    return InMemoryEventStore(id_factory=lambda: UUID(int=next(counter)))


def ingest(
    store: InMemoryEventStore,
    *,
    content: str,
    memory_type: MemoryType = MemoryType.EPISODIC,
    source: ProvenanceSource = ProvenanceSource.DECLARED,
    user_id: UserId = FIXED_USER,
    now: datetime = FIXED_NOW,
) -> Event:
    """Append one ``ingested`` event."""
    return store.append(
        user_id=user_id,
        payload=IngestedPayload(content=content, memory_type=memory_type),
        source=source,
        now=now,
    )


def correct(
    store: InMemoryEventStore,
    *,
    target: MemoryId,
    content: str,
    source: ProvenanceSource = ProvenanceSource.DECLARED,
    user_id: UserId = FIXED_USER,
    now: datetime = FIXED_NOW,
) -> Event:
    """Append one ``corrected`` event replacing ``target``'s content."""
    return store.append(
        user_id=user_id,
        payload=CorrectedPayload(target_memory_id=target, content=content),
        source=source,
        now=now,
    )


def delete(
    store: InMemoryEventStore,
    *,
    targets: tuple[MemoryId, ...],
    source: ProvenanceSource = ProvenanceSource.DECLARED,
    user_id: UserId = FIXED_USER,
    now: datetime = FIXED_NOW,
) -> Event:
    """Append one ``deleted`` event tombstoning ``targets``."""
    return store.append(
        user_id=user_id,
        payload=DeletedPayload(target_memory_ids=targets),
        source=source,
        now=now,
    )


# ---------------------------------------------------------------------------
# Standalone Memory examples - one per epistemic-relevant source, direct
# construction (not via ingest()): M2 has no engine that infers a memory, so
# the "inferred" example exists only to prove the *type* can represent one.
# ---------------------------------------------------------------------------


def declared_memory_example() -> Memory:
    """A direct user statement: "I value work-life balance."."""
    return Memory(
        id=MemoryId(uuid4()),
        user_id=FIXED_USER,
        type=MemoryType.SEMANTIC,
        content="I value work-life balance.",
        source=ProvenanceSource.DECLARED,
        occurred_at=None,
        origin_event_seq=1,
        projector_version=MEMORY_PROJECTOR_VERSION,
    )


def observed_memory_example() -> Memory:
    """A recorded decision, not a statement: "Logged decision: rejected the Berlin offer."."""
    return Memory(
        id=MemoryId(uuid4()),
        user_id=FIXED_USER,
        type=MemoryType.DECISION,
        content="Logged decision: rejected the Berlin offer.",
        source=ProvenanceSource.OBSERVED,
        occurred_at=FIXED_NOW.date(),
        origin_event_seq=1,
        projector_version=MEMORY_PROJECTOR_VERSION,
    )


def inferred_memory_example() -> Memory:
    """A memory as a future engine would eventually record one; not produced by any M2 code path."""
    return Memory(
        id=MemoryId(uuid4()),
        user_id=FIXED_USER,
        type=MemoryType.SEMANTIC,
        content="Appears to prioritise stability over salary.",
        source=ProvenanceSource.INFERRED,
        occurred_at=None,
        origin_event_seq=1,
        projector_version=MEMORY_PROJECTOR_VERSION,
    )


def uncertain_belief_reference() -> tuple[BeliefType, UUID]:
    """A belief with no recorded evidence at all.

    ``classify_epistemic_state(None)`` is what a caller reports for exactly
    this case: not a stored "uncertain" value, but the honest read of an
    empty ``EvidenceStore.for_belief(...)`` result.
    """
    return BeliefType.PREFERENCE, uuid4()


# ---------------------------------------------------------------------------
# Scenarios - built through a real store, so they exercise append + fold end
# to end, not just the Memory type in isolation.
# ---------------------------------------------------------------------------


def corrected_memory_scenario() -> tuple[InMemoryEventStore, MemoryProjectionState]:
    """ingested -> corrected: the commute story, then a fuller version of it."""
    store = deterministic_store()
    original = ingest(
        store,
        content="I previously rejected an offer because the commute was too long.",
    )
    correct(
        store,
        target=MemoryId(original.id),
        content="I rejected the offer mainly over pay; the commute was a secondary factor.",
    )
    state = fold_memory_events(FIXED_USER, store.read_stream(FIXED_USER))
    return store, state


def short_event_stream() -> tuple[InMemoryEventStore, tuple[Event, ...]]:
    """Three events: two ingests, then a correction of the first. e1 -> e2 -> e3."""
    store = deterministic_store()
    e1 = ingest(store, content="I care a lot about growth opportunities.")
    ingest(
        store,
        content="I turned down a raise to keep a flexible schedule.",
        memory_type=MemoryType.DECISION,
    )
    correct(
        store,
        target=MemoryId(e1.id),
        content="I care about growth, but not at the cost of my schedule.",
    )
    return store, store.read_stream(FIXED_USER)


def memory_with_evidence_scenario() -> tuple[Memory, Evidence, InMemoryEvidenceStore]:
    """A memory cited as evidence for a (fixture-only, not-yet-real) decision-factor belief."""
    memory = declared_memory_example()
    evidence_store = InMemoryEvidenceStore()
    evidence = evidence_store.record(
        Evidence(
            id=EvidenceId(uuid4()),
            user_id=FIXED_USER,
            belief_type=BeliefType.DECISION_FACTOR,
            belief_id=uuid4(),
            source_kind=EvidenceSourceKind.MEMORY,
            source_id=memory.id,
            weight=1.0,
            polarity=Polarity.SUPPORT,
            engine_version="m2-fixture",
            created_at=FIXED_NOW,
        )
    )
    return memory, evidence, evidence_store
