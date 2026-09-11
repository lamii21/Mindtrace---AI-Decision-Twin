"""The event vocabulary and the immutable event record.

Mirrors ``docs/architecture/02-domain-model.md`` AG-2 and ADR-001: the
append-only event log is MINDTRACE's only source of truth for user knowledge.
An :class:`Event` is never mutated after construction (frozen, and the only
way to make one is :meth:`~mindtrace.events.store.EventStore.append`, which
this module never calls itself).

``MemoryEventType`` declares all five Phase-0-approved event types, but M2
only defines - and can construct - typed payloads for the three it actually
projects: ``ingested``, ``corrected``, ``deleted``. ``elicitation_answered``
and ``outcome_recorded`` wait for the milestones that produce them (the Twin
Interview, decision outcomes) rather than getting a speculative payload shape
guessed at now.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from mindtrace.domain.enums import MemoryType, ProvenanceSource
from mindtrace.domain.errors import DomainError
from mindtrace.domain.ids import EventId, MemoryId, UserId
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


EventPayload = IngestedPayload | CorrectedPayload | DeletedPayload

_PAYLOAD_MODELS: dict[MemoryEventType, type[EventPayload]] = {
    MemoryEventType.INGESTED: IngestedPayload,
    MemoryEventType.CORRECTED: CorrectedPayload,
    MemoryEventType.DELETED: DeletedPayload,
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
            DomainError: for ``elicitation_answered``/``outcome_recorded`` -
                no typed payload is modelled yet (see module docstring).
        """
        model = _PAYLOAD_MODELS.get(self.type)
        if model is None:
            msg = f"no typed payload model for event type {self.type.value!r} yet"
            raise DomainError(msg)
        return model.model_validate(self.payload)
