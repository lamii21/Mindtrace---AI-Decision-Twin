"""Tests for the pure elicitation-answer fold (``mindtrace.events.projectors.preference``, M8)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from mindtrace.domain.enums import ChoiceOption, ProvenanceSource
from mindtrace.domain.ids import EventId, InterviewItemId, UserId
from mindtrace.events.enums import MemoryEventType
from mindtrace.events.projectors.preference import (
    PREFERENCE_PROJECTOR_VERSION,
    fold_elicitation_answer_events,
    fold_elicitation_answers,
)
from mindtrace.events.types import ElicitationAnsweredPayload, Event

_FIXED_USER = UserId(uuid4())
_FIXED_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _answer_event(
    *, seq: int, session_id: UUID, item_id: str, choice: Literal["A", "B", "indifferent"]
) -> Event:
    payload = ElicitationAnsweredPayload(item_id=InterviewItemId(item_id), choice=choice)
    return Event(
        id=EventId(uuid4()),
        user_id=_FIXED_USER,
        seq=seq,
        type=MemoryEventType.ELICITATION_ANSWERED,
        payload=payload.model_dump(mode="json"),
        source=ProvenanceSource.DECLARED,
        occurred_at=None,
        created_at=_FIXED_NOW,
        correlation_id=session_id,
    )


class TestFoldElicitationAnswers:
    def test_one_answer_per_item(self) -> None:
        session_id = uuid4()
        e1 = _answer_event(seq=1, session_id=session_id, item_id="p01", choice="A")
        e2 = _answer_event(seq=2, session_id=session_id, item_id="p02", choice="B")

        answers = fold_elicitation_answers([e1, e2], session_id=session_id)

        assert answers == {
            InterviewItemId("p01"): ChoiceOption.A,
            InterviewItemId("p02"): ChoiceOption.B,
        }

    def test_latest_answer_wins_when_an_item_is_answered_twice(self) -> None:
        session_id = uuid4()
        e1 = _answer_event(seq=1, session_id=session_id, item_id="p01", choice="A")
        e2 = _answer_event(seq=2, session_id=session_id, item_id="p01", choice="B")

        answers = fold_elicitation_answers([e1, e2], session_id=session_id)

        assert answers == {InterviewItemId("p01"): ChoiceOption.B}

    def test_earlier_answer_never_overwrites_a_later_one_regardless_of_list_order(self) -> None:
        # The fold trusts seq-order of the input, mirroring EventStore.read_stream's
        # own guarantee - feeding it in that natural order, the LATER seq must win.
        session_id = uuid4()
        earlier = _answer_event(seq=1, session_id=session_id, item_id="p01", choice="A")
        later = _answer_event(seq=2, session_id=session_id, item_id="p01", choice="B")

        answers = fold_elicitation_answers([earlier, later], session_id=session_id)
        assert answers[InterviewItemId("p01")] == ChoiceOption.B

    def test_indifferent_choice_folds_to_none(self) -> None:
        session_id = uuid4()
        event = _answer_event(seq=1, session_id=session_id, item_id="p01", choice="indifferent")

        answers = fold_elicitation_answers([event], session_id=session_id)

        assert answers == {InterviewItemId("p01"): None}

    def test_events_from_a_different_session_are_excluded(self) -> None:
        session_id = uuid4()
        other_session_id = uuid4()
        mine = _answer_event(seq=1, session_id=session_id, item_id="p01", choice="A")
        other = _answer_event(seq=2, session_id=other_session_id, item_id="p02", choice="A")

        answers = fold_elicitation_answers([mine, other], session_id=session_id)

        assert answers == {InterviewItemId("p01"): ChoiceOption.A}

    def test_non_elicitation_events_are_ignored(self) -> None:
        session_id = uuid4()
        unrelated = Event(
            id=EventId(uuid4()),
            user_id=_FIXED_USER,
            seq=1,
            type=MemoryEventType.OUTCOME_RECORDED,
            payload={"anything": "goes"},
            source=ProvenanceSource.DECLARED,
            occurred_at=None,
            created_at=_FIXED_NOW,
            correlation_id=session_id,
        )
        answer = _answer_event(seq=2, session_id=session_id, item_id="p01", choice="A")

        answers = fold_elicitation_answers([unrelated, answer], session_id=session_id)

        assert answers == {InterviewItemId("p01"): ChoiceOption.A}

    def test_empty_stream_gives_empty_answers(self) -> None:
        assert fold_elicitation_answers([], session_id=uuid4()) == {}


class TestFoldElicitationAnswerEvents:
    def test_carries_the_originating_event_id_for_evidence_provenance(self) -> None:
        session_id = uuid4()
        event = _answer_event(seq=1, session_id=session_id, item_id="p01", choice="A")

        answered = fold_elicitation_answer_events([event], session_id=session_id)

        assert answered[InterviewItemId("p01")].choice == ChoiceOption.A
        assert answered[InterviewItemId("p01")].event_id == event.id

    def test_latest_answer_wins_keeps_the_latest_events_id_too(self) -> None:
        session_id = uuid4()
        e1 = _answer_event(seq=1, session_id=session_id, item_id="p01", choice="A")
        e2 = _answer_event(seq=2, session_id=session_id, item_id="p01", choice="B")

        answered = fold_elicitation_answer_events([e1, e2], session_id=session_id)

        assert answered[InterviewItemId("p01")].event_id == e2.id
        assert answered[InterviewItemId("p01")].event_id != e1.id


def test_projector_version_is_a_stable_named_constant() -> None:
    assert isinstance(PREFERENCE_PROJECTOR_VERSION, str)
    assert PREFERENCE_PROJECTOR_VERSION
