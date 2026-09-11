"""Folding a user's event stream into the current memory state. Pure; no I/O.

``fold_memory_events`` is the one function this milestone's central claim rests
on: same events in, same :class:`MemoryProjectionState` out, every time
(M2 s11). It touches no clock, no randomness, no network, no database - the
only "time" it ever uses is the timestamp already recorded on an event
(``event.created_at``), copied forward, never read fresh.

A projected ``Memory``'s id is its originating event's id
(``MemoryId(event.id)``) - one identity assignment, at append time, by the
event store; the projector never mints a new one, so there is nothing here
that could disagree with itself on replay.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from mindtrace.domain.errors import DomainError
from mindtrace.domain.ids import MemoryId, UserId
from mindtrace.domain.memory import Memory
from mindtrace.events.enums import MemoryEventType
from mindtrace.events.types import CorrectedPayload, DeletedPayload, Event, IngestedPayload

MEMORY_PROJECTOR_VERSION = "1"

_FrozenModel = ConfigDict(frozen=True, extra="forbid")


class MemoryProjectionState(BaseModel):
    """The result of folding one user's event stream: every memory, current or not.

    Tombstoned (``deleted_at`` set) and superseded (``superseded_by`` set)
    rows are kept, not dropped - a future "what did I use to believe" or
    deletion-audit view needs them; :attr:`active_memories` is what a normal
    read uses.
    """

    model_config = _FrozenModel

    user_id: UserId
    memories: dict[MemoryId, Memory]
    last_seq: int

    @property
    def active_memories(self) -> tuple[Memory, ...]:
        """Memories that are neither superseded nor deleted."""
        return tuple(m for m in self.memories.values() if m.is_current)

    def get(self, memory_id: MemoryId) -> Memory:
        """Return the memory with ``memory_id``, current or not.

        Raises:
            KeyError: if no memory with that id was ever folded.
        """
        return self.memories[memory_id]


def fold_memory_events(user_id: UserId, events: Sequence[Event]) -> MemoryProjectionState:
    """Fold ``user_id``'s full, seq-ordered event stream into a :class:`MemoryProjectionState`.

    Raises:
        DomainError: if any event belongs to a different user, if ``seq`` is
            not exactly ``1, 2, 3, ...`` in order (catches duplicate and
            missing sequence numbers alike), or if a ``corrected``/``deleted``
            event targets a memory that does not currently exist or is
            already superseded/deleted.
    """
    memories: dict[MemoryId, Memory] = {}
    expected_seq = 1

    for event in events:
        if event.user_id != user_id:
            msg = f"event {event.id} belongs to user {event.user_id}, not {user_id}"
            raise DomainError(msg)
        if event.seq != expected_seq:
            msg = f"event {event.id} has seq={event.seq}, expected the next seq={expected_seq}"
            raise DomainError(msg)
        expected_seq += 1

        if event.type is MemoryEventType.INGESTED:
            _apply_ingested(memories, user_id, event)
        elif event.type is MemoryEventType.CORRECTED:
            _apply_corrected(memories, user_id, event)
        elif event.type is MemoryEventType.DELETED:
            _apply_deleted(memories, event)
        # ELICITATION_ANSWERED / OUTCOME_RECORDED: not this projector's concern (M2 s6).

    return MemoryProjectionState(user_id=user_id, memories=memories, last_seq=expected_seq - 1)


def _apply_ingested(memories: dict[MemoryId, Memory], user_id: UserId, event: Event) -> None:
    payload = IngestedPayload.model_validate(event.payload)
    memory_id = MemoryId(event.id)
    memories[memory_id] = Memory(
        id=memory_id,
        user_id=user_id,
        type=payload.memory_type,
        content=payload.content,
        source=event.source,
        occurred_at=event.occurred_at,
        origin_event_seq=event.seq,
        projector_version=MEMORY_PROJECTOR_VERSION,
    )


def _apply_corrected(memories: dict[MemoryId, Memory], user_id: UserId, event: Event) -> None:
    payload = CorrectedPayload.model_validate(event.payload)
    target = memories.get(payload.target_memory_id)
    if target is None or not target.is_current:
        msg = (
            f"corrected event {event.id} targets memory {payload.target_memory_id}, "
            "which does not exist or is no longer live"
        )
        raise DomainError(msg)

    new_id = MemoryId(event.id)
    memories[new_id] = Memory(
        id=new_id,
        user_id=user_id,
        type=target.type,
        content=payload.content,
        source=event.source,
        occurred_at=event.occurred_at,
        origin_event_seq=event.seq,
        projector_version=MEMORY_PROJECTOR_VERSION,
    )
    memories[target.id] = target.model_copy(update={"superseded_by": new_id})


def _apply_deleted(memories: dict[MemoryId, Memory], event: Event) -> None:
    payload = DeletedPayload.model_validate(event.payload)
    for memory_id in payload.target_memory_ids:
        target = memories.get(memory_id)
        if target is None or not target.is_current:
            msg = (
                f"deleted event {event.id} targets memory {memory_id}, "
                "which does not exist or is no longer live"
            )
            raise DomainError(msg)
        memories[memory_id] = target.model_copy(
            update={"deleted_at": event.created_at, "deleted_by_event_seq": event.seq}
        )
