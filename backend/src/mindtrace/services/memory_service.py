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
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from mindtrace.db.crypto import KeyProvider
from mindtrace.db.event_store import PostgresEventStore
from mindtrace.db.repositories import memory_repository
from mindtrace.domain.enums import MemoryType, ProvenanceSource
from mindtrace.domain.ids import MemoryId, UserId
from mindtrace.domain.memory import Memory
from mindtrace.events.evidence_store import InMemoryEvidenceStore
from mindtrace.events.projectors.memory import MemoryProjectionState, fold_memory_events
from mindtrace.events.rederive import DeletionImpact, apply_deletion, preview_deletion
from mindtrace.events.types import IngestedPayload
from mindtrace.services.errors import ResourceNotFoundError

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
) -> DeletionImpact:
    """Dry-run: compute what deleting ``memory_ids`` would affect, changing nothing.

    Raises:
        ResourceNotFoundError: a memory id is unknown to ``user_id`` - either
            it never existed or belongs to someone else. ``preview_deletion``
            (M2, unmodified) raises ``KeyError`` for that case; RLS already
            makes "doesn't exist" and "not yours" indistinguishable by
            scoping ``state`` to ``user_id``, so both collapse to 404 here.
    """
    state = _current_state(user_id=user_id, key_provider=key_provider)
    try:
        return preview_deletion(state, memory_ids, evidence_store=InMemoryEvidenceStore())
    except KeyError as exc:
        msg = f"memory {exc.args[0]} not found"
        raise ResourceNotFoundError(msg) from exc


def apply_delete(
    *, user_id: UserId, memory_ids: tuple[MemoryId, ...], key_provider: KeyProvider, now: datetime
) -> tuple[DeletionImpact, UUID]:
    """Apply the deletion: append a ``deleted`` event, re-derive, persist.

    Returns ``(impact, job_id)`` - ``job_id`` is a fresh id matching the
    documented ``202 {job_id}`` response shape; the work itself already
    completed synchronously by the time this returns (see module docstring).

    Raises:
        ResourceNotFoundError: see :func:`preview_delete` - same translation
            of the underlying ``KeyError`` applies here.
    """
    store = PostgresEventStore(key_provider=key_provider)
    state = _current_state(user_id=user_id, key_provider=key_provider)
    try:
        impact, new_state = apply_deletion(
            store,
            state,
            memory_ids,
            evidence_store=InMemoryEvidenceStore(),
            source=ProvenanceSource.DECLARED,
            now=now,
        )
    except KeyError as exc:
        msg = f"memory {exc.args[0]} not found"
        raise ResourceNotFoundError(msg) from exc
    for memory in new_state.memories.values():
        memory_repository.upsert_memory(memory=memory, key_provider=key_provider)
    return impact, uuid4()


def _current_state(*, user_id: UserId, key_provider: KeyProvider) -> MemoryProjectionState:
    store = PostgresEventStore(key_provider=key_provider)
    return fold_memory_events(user_id, store.read_stream(user_id))
