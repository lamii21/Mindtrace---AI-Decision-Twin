"""The event store port.

Domain (and application code above it) defines what it needs; infrastructure
implements it (M2 s15). This ``Protocol`` is the whole contract -
:mod:`mindtrace.events.in_memory_store` is one implementation, used directly
today and by tests once a PostgreSQL-backed one exists (M4+, per
``docs/11-roadmap-milestones.md``); nothing here or in
:mod:`mindtrace.events.projectors` or :mod:`mindtrace.events.rederive` knows
or cares which.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from mindtrace.domain.enums import ProvenanceSource
from mindtrace.domain.ids import EventId, UserId
from mindtrace.events.types import Event, EventPayload


class EventStore(Protocol):
    """An append-only, per-user-ordered log of :class:`~mindtrace.events.types.Event`.

    Deliberately two methods: everything M2 needs, nothing speculative
    (M2 s14). ``append`` is the *only* way an ``Event`` comes into existence -
    it assigns identity (``id``) and per-user order (``seq``); callers never
    construct one directly.
    """

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
        """Append one event to ``user_id``'s stream and return the stored record.

        ``now`` is supplied by the caller, never read from the wall clock
        internally (Invariant A) - an implementation may default it at its own
        boundary (e.g. the API layer), but the port itself takes no such
        shortcut, so store behaviour stays exactly reproducible in tests.
        """
        ...

    def read_stream(self, user_id: UserId, *, since_seq: int = 0) -> tuple[Event, ...]:
        """Return ``user_id``'s events with ``seq > since_seq``, in order.

        An unknown ``user_id`` returns an empty tuple, not an error - an empty
        stream and a never-seen user are indistinguishable to a store that
        holds no side information about users (that belongs to ``AG-1 User``,
        a different aggregate).
        """
        ...
