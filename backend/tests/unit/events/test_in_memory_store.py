"""Tests for the in-memory event store (``mindtrace.events.in_memory_store``)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from mindtrace.domain.enums import MemoryType, ProvenanceSource
from mindtrace.domain.ids import MemoryId, UserId
from mindtrace.events.enums import MemoryEventType
from mindtrace.events.in_memory_store import InMemoryEventStore
from mindtrace.events.types import IngestedPayload
from tests.support.memory_fixtures import (
    FIXED_NOW,
    FIXED_USER,
    OTHER_USER,
    correct,
    deterministic_store,
    ingest,
)


class TestAppendOnlySemantics:
    def test_seq_is_gap_free_and_starts_at_one(self) -> None:
        store = deterministic_store()
        e1 = ingest(store, content="first")
        e2 = ingest(store, content="second")
        e3 = ingest(store, content="third")
        assert (e1.seq, e2.seq, e3.seq) == (1, 2, 3)

    def test_each_user_has_an_independent_sequence(self) -> None:
        store = deterministic_store()
        ingest(store, content="a", user_id=UserId(uuid4()))
        first_for_other = ingest(store, content="b", user_id=OTHER_USER)
        assert first_for_other.seq == 1  # not 2 - a different user's stream, not shared

    def test_correction_is_a_new_event_not_a_mutation(self) -> None:
        store = deterministic_store()
        original = ingest(store, content="original")
        correct(store, target=MemoryId(original.id), content="corrected")

        stream = store.read_stream(FIXED_USER)
        assert len(stream) == 2
        assert stream[0].type is MemoryEventType.INGESTED
        assert stream[0].payload["content"] == "original"  # the original event itself never changes
        assert stream[1].type is MemoryEventType.CORRECTED

    def test_event_returned_by_append_is_frozen(self) -> None:
        store = deterministic_store()
        event = ingest(store, content="x")
        assert event.model_config.get("frozen") is True

    def test_store_exposes_no_mutation_or_removal_method(self) -> None:
        public_methods = {name for name in dir(InMemoryEventStore) if not name.startswith("_")}
        assert public_methods == {"append", "read_stream"}

    def test_read_stream_returns_a_fresh_tuple_each_time(self) -> None:
        store = deterministic_store()
        ingest(store, content="x")
        first = store.read_stream(FIXED_USER)
        second = store.read_stream(FIXED_USER)
        assert first == second
        assert first is not second


class TestReadStream:
    def test_unknown_user_returns_empty_tuple(self) -> None:
        store = deterministic_store()
        assert store.read_stream(UserId(uuid4())) == ()

    def test_since_seq_filters_to_later_events_only(self) -> None:
        store = deterministic_store()
        e1 = ingest(store, content="a")
        e2 = ingest(store, content="b")
        e3 = ingest(store, content="c")

        assert store.read_stream(FIXED_USER, since_seq=1) == (e2, e3)
        assert store.read_stream(FIXED_USER, since_seq=3) == ()
        assert store.read_stream(FIXED_USER, since_seq=0) == (e1, e2, e3)

    def test_events_are_returned_in_order(self) -> None:
        store = deterministic_store()
        ingest(store, content="a")
        ingest(store, content="b")
        stream = store.read_stream(FIXED_USER)
        assert [e.seq for e in stream] == sorted(e.seq for e in stream)


class TestDeterministicIdFactory:
    def test_injected_id_factory_is_used(self) -> None:
        store = deterministic_store()
        e1 = ingest(store, content="a")
        e2 = ingest(store, content="b")
        assert e1.id != e2.id
        assert e1.id.int == 1  # UUID(int=1) from the deterministic factory
        assert e2.id.int == 2

    def test_now_is_taken_from_the_caller_not_the_wall_clock(self) -> None:
        store = deterministic_store()
        fixed = datetime(2020, 5, 17, 9, 30, tzinfo=UTC)
        event = store.append(
            user_id=UserId(uuid4()),
            payload=IngestedPayload(content="x", memory_type=MemoryType.EPISODIC),
            source=ProvenanceSource.DECLARED,
            now=fixed,
        )
        assert event.created_at == fixed
        assert event.created_at != FIXED_NOW  # proves it's not defaulting to some ambient value
