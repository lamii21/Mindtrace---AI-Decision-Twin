"""The event vocabulary and the immutable event record.

Mirrors ``docs/architecture/02-domain-model.md`` AG-2 and ADR-001: the
append-only event log is MINDTRACE's only source of truth for user knowledge.
An :class:`Event` is never mutated after construction (frozen, and the only
way to make one is :meth:`~mindtrace.events.store.EventStore.append`, which
this module never calls itself).

``MemoryEventType`` declares all five Phase-0-approved event types. M2
defined typed payloads for ``ingested``/``corrected``/``deleted``; M8 adds
``elicitation_answered`` (one interview answer - spec/07 §2/§4). This is the
*only* way an interview answer is ever persisted - there is no separate
interview-answer table (M8 planning s13/s17): the event log remains the
single source of truth, and routing through the existing
``PostgresEventStore.append()`` encrypts the payload exactly as every other
event already is, with zero new encryption-boundary code. ``outcome_recorded``
still waits for the milestone that produces it (decision outcomes, M9+).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from mindtrace.domain.enums import MemoryType, ProvenanceSource
from mindtrace.domain.errors import DomainError
from mindtrace.domain.ids import EventId, InterviewItemId, MemoryId, UserId
from mindtrace.events.enums import MemoryEventType

_FrozenModel = ConfigDict(frozen=True, extra="forbid")


class IngestedPayload(BaseModel):
    """A new fact the user declared or an observation the system recorded."""

    model_config = _FrozenModel

    event_type: ClassVar[MemoryEventType] = MemoryEventType.INGESTED

    content: str = Field(min_length=1)
    memory_type: MemoryType


class CorrectedPayload(BaseModel):
    """A replacement for a memory's content. The target must currently be live."""

    model_config = _FrozenModel

    event_type: ClassVar[MemoryEventType] = MemoryEventType.CORRECTED

    target_memory_id: MemoryId
    content: str = Field(min_length=1)


class DeletedPayload(BaseModel):
    """A request to tombstone one or more currently-live memories."""

    model_config = _FrozenModel

    event_type: ClassVar[MemoryEventType] = MemoryEventType.DELETED

    target_memory_ids: tuple[MemoryId, ...] = Field(min_length=1)


class ElicitationAnsweredPayload(BaseModel):
    """One Twin Interview answer (spec/07 §2).

    Structured, never free text: an ``item_id`` referencing the versioned,
    non-secret ``interview.yaml`` bank, a forced choice, and an optional
    response latency. A session groups its events via ``Event.
    correlation_id`` (AG-2's own "request/session grouping" field) rather
    than a ``session_id`` duplicated into every payload. Answering the same
    ``item_id`` again within a session never edits this event - it appends a
    new one; finalisation (``engines/elicitation/finalize.py``) uses the
    latest answer per item.
    """

    model_config = _FrozenModel

    event_type: ClassVar[MemoryEventType] = MemoryEventType.ELICITATION_ANSWERED

    item_id: InterviewItemId
    choice: Literal["A", "B", "indifferent"]
    latency_ms: int | None = None


EventPayload = IngestedPayload | CorrectedPayload | DeletedPayload | ElicitationAnsweredPayload

_PAYLOAD_MODELS: dict[MemoryEventType, type[EventPayload]] = {
    MemoryEventType.INGESTED: IngestedPayload,
    MemoryEventType.CORRECTED: CorrectedPayload,
    MemoryEventType.DELETED: DeletedPayload,
    MemoryEventType.ELICITATION_ANSWERED: ElicitationAnsweredPayload,
}


class Event(BaseModel):
    """One immutable, ordered fact in a user's event stream.

    ``created_at`` and ``occurred_at`` are metadata: available to a projector
    for display or for copying forward into a projection, but never read to
    make a projector's *logic* branch (that would make replay depend on when
    it happens to run, breaking determinism - M2 s6/s11).
    """

    model_config = _FrozenModel

    id: EventId
    user_id: UserId
    seq: int
    type: MemoryEventType
    payload: dict[str, Any]
    source: ProvenanceSource
    occurred_at: date | None
    created_at: datetime
    causation_id: EventId | None = None
    correlation_id: UUID | None = None

    def typed_payload(self) -> EventPayload:
        """Parse ``payload`` into its typed form for ``self.type``.

        Raises:
            DomainError: for ``outcome_recorded`` - no typed payload is
                modelled yet (see module docstring).
        """
        model = _PAYLOAD_MODELS.get(self.type)
        if model is None:
            msg = f"no typed payload model for event type {self.type.value!r} yet"
            raise DomainError(msg)
        return model.model_validate(self.payload)
