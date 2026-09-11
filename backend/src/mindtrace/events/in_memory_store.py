"""An in-memory :class:`~mindtrace.events.store.EventStore`.

Real, not a stand-in that merely looks like one (M2 s4/s14): correct
append-only semantics, correct per-user gap-free ordering, correct isolation
between users - the same guarantees a PostgreSQL-backed store must give, minus
durability. It stays the store used in dev/tests even after a
PostgreSQL-backed one exists; this module does not pretend to *be* PostgreSQL,
it is a complete, independent implementation of the same small port.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from uuid import UUID, uuid4

from mindtrace.domain.enums import ProvenanceSource
from mindtrace.domain.ids import EventId, UserId
from mindtrace.events.types import Event, EventPayload


class InMemoryEventStore:
    """Process-local :class:`~mindtrace.events.store.EventStore`. Not thread-safe."""

    def __init__(self, *, id_factory: Callable[[], UUID] = uuid4) -> None:
        """``id_factory`` is injectable so tests can make event ids predictable."""
        self._id_factory = id_factory
        self._streams: dict[UserId, list[Event]] = {}

    def append(
        self,
        *,
        user_id: UserId,
        payload: EventPayload,
        source: ProvenanceSource,
        now: datetime,
        occurred_at: date | None = None,
        causation_id: EventId | None = None,
        correlation_id: UUID | None = None,
    ) -> Event:
        """See :meth:`mindtrace.events.store.EventStore.append`."""
        stream = self._streams.setdefault(user_id, [])
        event = Event(
            id=EventId(self._id_factory()),
            user_id=user_id,
            seq=len(stream) + 1,
            type=payload.event_type,
            payload=payload.model_dump(mode="json"),
            source=source,
            occurred_at=occurred_at,
            created_at=now,
            causation_id=causation_id,
            correlation_id=correlation_id,
        )
        stream.append(event)
        return event

    def read_stream(self, user_id: UserId, *, since_seq: int = 0) -> tuple[Event, ...]:
        """See :meth:`mindtrace.events.store.EventStore.read_stream`."""
        return tuple(e for e in self._streams.get(user_id, ()) if e.seq > since_seq)
