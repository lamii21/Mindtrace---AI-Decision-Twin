"""Folding a user's ``elicitation_answered`` events into one answer per item (M8).

Pure, like ``projectors/memory.py``: replay-only, no I/O, no clock. "Latest
answer wins" when the same ``item_id`` is answered more than once within a
session - the event log keeps every answer, append-only and never mutated;
this projector only decides which one counts when ``engines.elicitation.
finalize`` runs the batch update. A session's events are identified by
``Event.correlation_id`` (AG-2's own "request/session grouping" field), set
once at session creation and carried by every answer appended under it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from mindtrace.domain.enums import ChoiceOption
from mindtrace.domain.ids import EventId, InterviewItemId
from mindtrace.events.enums import MemoryEventType
from mindtrace.events.types import ElicitationAnsweredPayload, Event

PREFERENCE_PROJECTOR_VERSION = "1"


@dataclass(frozen=True)
class AnsweredItem:
    """One item's latest answer, plus the originating event's id (for Evidence provenance)."""

    choice: ChoiceOption | None
    event_id: EventId


def fold_elicitation_answer_events(
    events: Sequence[Event], *, session_id: UUID
) -> dict[InterviewItemId, AnsweredItem]:
    """The latest ``AnsweredItem`` per ``item_id`` for one session's answer events.

    ``events`` is assumed ``seq``-ordered (as ``EventStore.read_stream``
    already guarantees) - a later event for the same ``item_id`` overwrites
    an earlier one in the returned mapping, never the reverse.
    """
    answers: dict[InterviewItemId, AnsweredItem] = {}
    for event in events:
        if event.type is not MemoryEventType.ELICITATION_ANSWERED:
            continue
        if event.correlation_id != session_id:
            continue
        payload = ElicitationAnsweredPayload.model_validate(event.payload)
        answers[payload.item_id] = AnsweredItem(
            choice=_choice_from_str(payload.choice), event_id=event.id
        )
    return answers


def fold_elicitation_answers(
    events: Sequence[Event], *, session_id: UUID
) -> dict[InterviewItemId, ChoiceOption | None]:
    """The latest answer per ``item_id``, choice only.

    Matches ``engines.preference.interview``'s own
    ``choice: ChoiceOption | None`` convention (``None`` for
    ``"indifferent"``). Use :func:`fold_elicitation_answer_events` instead
    when the originating event id is also needed (e.g. Evidence provenance).
    """
    return {
        item_id: answered.choice
        for item_id, answered in fold_elicitation_answer_events(
            events, session_id=session_id
        ).items()
    }


def _choice_from_str(choice: str) -> ChoiceOption | None:
    if choice == "indifferent":
        return None
    return ChoiceOption(choice)


__all__ = [
    "PREFERENCE_PROJECTOR_VERSION",
    "AnsweredItem",
    "fold_elicitation_answer_events",
    "fold_elicitation_answers",
]
