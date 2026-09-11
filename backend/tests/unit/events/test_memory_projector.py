"""Tests for the pure memory fold (``mindtrace.events.projectors.memory``)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from mindtrace.domain.enums import MemoryType, ProvenanceSource
from mindtrace.domain.errors import DomainError
from mindtrace.domain.ids import EventId, MemoryId, UserId
from mindtrace.events.enums import MemoryEventType
from mindtrace.events.projectors.memory import MEMORY_PROJECTOR_VERSION, fold_memory_events
from mindtrace.events.types import CorrectedPayload, DeletedPayload, Event, IngestedPayload
from tests.support.memory_fixtures import (
    FIXED_NOW,
    FIXED_USER,
    correct,
    delete,
    deterministic_store,
    ingest,
    short_event_stream,
)


def _raw_event(*, seq: int, event_type: MemoryEventType, payload: dict[str, object]) -> Event:
    """A hand-built event, bypassing the store - for exercising fold-time integrity checks."""
    return Event(
        id=EventId(uuid4()),
        user_id=FIXED_USER,
        seq=seq,
        type=event_type,
        payload=payload,
        source=ProvenanceSource.DECLARED,
        occurred_at=None,
        created_at=FIXED_NOW,
    )


def _ingested_json(content: str) -> dict[str, object]:
    return IngestedPayload(content=content, memory_type=MemoryType.EPISODIC).model_dump(mode="json")


class TestSingleIngest:
    def test_one_ingested_event_produces_one_current_memory(self) -> None:
        store = deterministic_store()
        event = ingest(store, content="I value autonomy.", memory_type=MemoryType.SEMANTIC)

        state = fold_memory_events(FIXED_USER, store.read_stream(FIXED_USER))

        assert len(state.memories) == 1
        memory = state.get(MemoryId(event.id))
        assert memory.content == "I value autonomy."
        assert memory.type is MemoryType.SEMANTIC
        assert memory.source is ProvenanceSource.DECLARED
        assert memory.origin_event_seq == 1
        assert memory.projector_version == MEMORY_PROJECTOR_VERSION
        assert memory.is_current
        assert state.active_memories == (memory,)
        assert state.last_seq == 1


class TestCorrection:
    def test_e1_ingest_then_e2_correct_exact_expected_state(self) -> None:
        store = deterministic_store()
        e1 = ingest(store, content="original text")
        e2 = correct(store, target=MemoryId(e1.id), content="corrected text")

        state = fold_memory_events(FIXED_USER, store.read_stream(FIXED_USER))

        assert len(state.memories) == 2
        old = state.get(MemoryId(e1.id))
        new = state.get(MemoryId(e2.id))

        assert old.superseded_by == new.id
        assert not old.is_current
        assert old.content == "original text"  # the original row's content is untouched

        assert new.content == "corrected text"
        assert new.origin_event_seq == 2
        assert new.superseded_by is None
        assert new.is_current

        assert state.active_memories == (new,)

    def test_correcting_an_unknown_memory_raises(self) -> None:
        event = _raw_event(
            seq=1,
            event_type=MemoryEventType.CORRECTED,
            payload=CorrectedPayload(target_memory_id=MemoryId(uuid4()), content="x").model_dump(
                mode="json"
            ),
        )
        with pytest.raises(DomainError, match="does not exist or is no longer live"):
            fold_memory_events(FIXED_USER, (event,))

    def test_correcting_an_already_superseded_memory_raises(self) -> None:
        store = deterministic_store()
        e1 = ingest(store, content="v1")
        correct(store, target=MemoryId(e1.id), content="v2")
        correct(store, target=MemoryId(e1.id), content="v3-should-fail")  # e1 is no longer live

        with pytest.raises(DomainError, match="does not exist or is no longer live"):
            fold_memory_events(FIXED_USER, store.read_stream(FIXED_USER))


class TestDeletion:
    def test_e1_ingest_then_e2_delete_tombstones_but_keeps_the_row(self) -> None:
        store = deterministic_store()
        e1 = ingest(store, content="forget me")
        e2 = delete(store, targets=(MemoryId(e1.id),))

        state = fold_memory_events(FIXED_USER, store.read_stream(FIXED_USER))

        memory = state.get(MemoryId(e1.id))
        assert memory.deleted_at == e2.created_at
        assert memory.deleted_by_event_seq == e2.seq
        assert not memory.is_current
        assert state.active_memories == ()
        assert MemoryId(e1.id) in state.memories  # tombstoned, not physically removed

    def test_deleting_an_unknown_memory_raises(self) -> None:
        event = _raw_event(
            seq=1,
            event_type=MemoryEventType.DELETED,
            payload=DeletedPayload(target_memory_ids=(MemoryId(uuid4()),)).model_dump(mode="json"),
        )
        with pytest.raises(DomainError, match="does not exist or is no longer live"):
            fold_memory_events(FIXED_USER, (event,))

    def test_deleting_an_already_deleted_memory_raises(self) -> None:
        store = deterministic_store()
        e1 = ingest(store, content="x")
        delete(store, targets=(MemoryId(e1.id),))
        delete(store, targets=(MemoryId(e1.id),))  # second delete of the same memory

        with pytest.raises(DomainError, match="does not exist or is no longer live"):
            fold_memory_events(FIXED_USER, store.read_stream(FIXED_USER))


class TestIntegrityChecks:
    def test_conflicting_user_id_raises(self) -> None:
        store = deterministic_store()
        ingest(store, content="a")
        other_user_event = ingest(store, content="b", user_id=UserId(uuid4()))
        # Folding FIXED_USER's stream together with an event that actually belongs to a
        # different user must be rejected outright, not silently mixed in.
        with pytest.raises(DomainError, match="belongs to user"):
            fold_memory_events(FIXED_USER, (other_user_event,))

    def test_duplicate_seq_raises(self) -> None:
        e1 = _raw_event(seq=1, event_type=MemoryEventType.INGESTED, payload=_ingested_json("a"))
        duplicate = e1.model_copy(update={"id": EventId(uuid4())})  # same seq=1 again
        with pytest.raises(DomainError, match="expected the next seq"):
            fold_memory_events(FIXED_USER, (e1, duplicate))

    def test_missing_seq_raises(self) -> None:
        e1 = _raw_event(seq=1, event_type=MemoryEventType.INGESTED, payload=_ingested_json("a"))
        e3 = e1.model_copy(update={"id": EventId(uuid4()), "seq": 3})  # skips seq=2
        with pytest.raises(DomainError, match="expected the next seq"):
            fold_memory_events(FIXED_USER, (e1, e3))

    def test_empty_event_list_yields_empty_state(self) -> None:
        state = fold_memory_events(FIXED_USER, ())
        assert state.memories == {}
        assert state.active_memories == ()
        assert state.last_seq == 0


class TestUnprojectedEventTypes:
    def test_elicitation_answered_and_outcome_recorded_are_skipped_not_rejected(self) -> None:
        e1 = ingest(deterministic_store(), content="a")
        skipped = _raw_event(
            seq=2, event_type=MemoryEventType.ELICITATION_ANSWERED, payload={"anything": "goes"}
        )
        state = fold_memory_events(FIXED_USER, (e1, skipped))
        assert len(state.memories) == 1  # the ingest was projected; the other event was ignored
        assert state.last_seq == 2  # but seq-order bookkeeping still advances past it


class TestGoldenReplay:
    def test_short_event_stream_produces_the_exact_expected_state(self) -> None:
        _store, events = short_event_stream()
        assert [e.type for e in events] == [
            MemoryEventType.INGESTED,
            MemoryEventType.INGESTED,
            MemoryEventType.CORRECTED,
        ]

        state = fold_memory_events(FIXED_USER, events)

        assert len(state.memories) == 3  # 2 ingested rows + 1 corrected row replacing the first
        assert len(state.active_memories) == 2  # the corrected original is no longer active
        first_original = state.get(MemoryId(events[0].id))
        assert not first_original.is_current
        assert first_original.content == "I care a lot about growth opportunities."
        replacement = state.get(MemoryId(events[2].id))
        assert replacement.content == "I care about growth, but not at the cost of my schedule."
        second = state.get(MemoryId(events[1].id))
        assert second.is_current
        assert second.content == "I turned down a raise to keep a flexible schedule."
