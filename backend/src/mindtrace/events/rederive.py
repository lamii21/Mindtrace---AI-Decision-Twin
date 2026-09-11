"""Rebuilding state from history, and previewing/applying a deletion.

Two things this module proves are possible without them being impossible by
construction (M2 s12/s13):

- **Rebuildability**: :func:`rederive` discards nothing and trusts nothing but
  the event log - the same guarantee a cache-invalidation bug could quietly
  break, which is exactly why this exists as one small, tested function
  rather than being left implicit.
- **Deletion that doesn't make a promise it can't keep**: :func:`preview_deletion`
  reports real, computed impact (which memories, which evidence edges) from
  what M2 actually has - Memory and Evidence. It does not claim to recompute
  downstream beliefs (there are none yet), crypto-shred anything, or resolve
  a topic into a set of memories (that needs semantic matching M2 doesn't
  have) - see ``docs/PHASE-0-REVIEW.md`` s7 for why that line is drawn here.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from mindtrace.domain.enums import EvidenceSourceKind, ProvenanceSource
from mindtrace.domain.errors import DomainError
from mindtrace.domain.evidence import Evidence
from mindtrace.domain.ids import MemoryId, UserId
from mindtrace.events.evidence_store import EvidenceStore
from mindtrace.events.projectors.memory import MemoryProjectionState, fold_memory_events
from mindtrace.events.store import EventStore
from mindtrace.events.types import DeletedPayload


def rederive(store: EventStore, user_id: UserId) -> MemoryProjectionState:
    """Rebuild ``user_id``'s current memory state from scratch, from the event log alone.

    Reads the full stream and folds it; nothing else contributes. Calling this
    twice in a row (no events appended in between) returns equal states.
    """
    events = store.read_stream(user_id)
    return fold_memory_events(user_id, events)


class DeletionImpact(BaseModel):
    """What deleting ``memory_ids`` would (or did) affect."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_ids: tuple[MemoryId, ...]
    affected_evidence: tuple[Evidence, ...]


def preview_deletion(
    state: MemoryProjectionState,
    memory_ids: tuple[MemoryId, ...],
    *,
    evidence_store: EvidenceStore,
) -> DeletionImpact:
    """Compute what deleting ``memory_ids`` would affect, without changing anything.

    Raises:
        KeyError: if a memory id is not present in ``state`` at all.
        DomainError: if a memory id names one that is already deleted.
    """
    for memory_id in memory_ids:
        memory = state.get(memory_id)
        if memory.deleted_at is not None:
            msg = f"memory {memory_id} is already deleted"
            raise DomainError(msg)

    seen: dict[UUID, Evidence] = {}
    for memory_id in memory_ids:
        for evidence in evidence_store.for_source(EvidenceSourceKind.MEMORY, memory_id):
            seen[evidence.id] = evidence

    return DeletionImpact(memory_ids=memory_ids, affected_evidence=tuple(seen.values()))


def apply_deletion(
    store: EventStore,
    state: MemoryProjectionState,
    memory_ids: tuple[MemoryId, ...],
    *,
    evidence_store: EvidenceStore,
    source: ProvenanceSource,
    now: datetime,
    occurred_at: date | None = None,
) -> tuple[DeletionImpact, MemoryProjectionState]:
    """Preview, then actually perform, deleting ``memory_ids``.

    Appends one ``deleted`` event and re-derives state from scratch, so the
    returned state is exactly what :func:`rederive` would produce - there is
    no separate "apply the delta" code path to fall out of sync with replay.
    """
    impact = preview_deletion(state, memory_ids, evidence_store=evidence_store)
    store.append(
        user_id=state.user_id,
        payload=DeletedPayload(target_memory_ids=memory_ids),
        source=source,
        now=now,
        occurred_at=occurred_at,
    )
    return impact, rederive(store, state.user_id)
