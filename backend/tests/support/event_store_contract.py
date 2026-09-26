"""The one behavioral contract every `EventStore` adapter must satisfy.

A mixin, not a standalone test module: a concrete test class subclasses this
and overrides the ``store``/``user_a``/``user_b`` fixtures to point at a
specific adapter. Both ``InMemoryEventStore`` and ``PostgresEventStore`` run
the *exact same* test bodies - there is deliberately no separate, drifting
"Postgres version" of these assertions (M6-Persistence/Foundation planning
s16).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from mindtrace.domain.enums import MemoryType, ProvenanceSource
from mindtrace.domain.ids import MemoryId, UserId
from mindtrace.events.enums import MemoryEventType
from mindtrace.events.store import EventStore
from mindtrace.events.types import CorrectedPayload, IngestedPayload

FIXED_NOW = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)


class EventStoreContractTests:
    """Subclass and override ``store``/``user_a``/``user_b`` (pytest fixtures)."""

    @pytest.fixture
    def store(self) -> EventStore:
        raise NotImplementedError

    @pytest.fixture
    def user_a(self) -> UserId:
        raise NotImplementedError

    @pytest.fixture
    def user_b(self) -> UserId:
        raise NotImplementedError

    def test_first_append_gets_seq_one(self, store: EventStore, user_a: UserId) -> None:
        event = store.append(
            user_id=user_a,
            payload=IngestedPayload(content="first", memory_type=MemoryType.EPISODIC),
            source=ProvenanceSource.DECLARED,
            now=FIXED_NOW,
        )
        assert event.seq == 1

    def test_seq_is_gap_free_across_appends(self, store: EventStore, user_a: UserId) -> None:
        seqs = [
            store.append(
                user_id=user_a,
                payload=IngestedPayload(content=f"e{i}", memory_type=MemoryType.EPISODIC),
                source=ProvenanceSource.DECLARED,
                now=FIXED_NOW,
            ).seq
            for i in range(3)
        ]
        assert seqs == [1, 2, 3]

    def test_each_user_has_an_independent_sequence(
        self, store: EventStore, user_a: UserId, user_b: UserId
    ) -> None:
        store.append(
            user_id=user_a,
            payload=IngestedPayload(content="a", memory_type=MemoryType.EPISODIC),
            source=ProvenanceSource.DECLARED,
            now=FIXED_NOW,
        )
        first_for_b = store.append(
            user_id=user_b,
            payload=IngestedPayload(content="b", memory_type=MemoryType.EPISODIC),
            source=ProvenanceSource.DECLARED,
            now=FIXED_NOW,
        )
        assert first_for_b.seq == 1

    def test_read_stream_returns_events_in_seq_order(
        self, store: EventStore, user_a: UserId
    ) -> None:
        for i in range(3):
            store.append(
                user_id=user_a,
                payload=IngestedPayload(content=f"e{i}", memory_type=MemoryType.EPISODIC),
                source=ProvenanceSource.DECLARED,
                now=FIXED_NOW,
            )
        stream = store.read_stream(user_a)
        assert [e.seq for e in stream] == [1, 2, 3]

    def test_since_seq_filters_to_later_events_only(
        self, store: EventStore, user_a: UserId
    ) -> None:
        for i in range(3):
            store.append(
                user_id=user_a,
                payload=IngestedPayload(content=f"e{i}", memory_type=MemoryType.EPISODIC),
                source=ProvenanceSource.DECLARED,
                now=FIXED_NOW,
            )
        assert [e.seq for e in store.read_stream(user_a, since_seq=1)] == [2, 3]
        assert store.read_stream(user_a, since_seq=3) == ()

    def test_unknown_user_returns_empty_stream_not_an_error(self, store: EventStore) -> None:
        assert store.read_stream(UserId(uuid4())) == ()

    def test_payload_round_trips_exactly(self, store: EventStore, user_a: UserId) -> None:
        store.append(
            user_id=user_a,
            payload=IngestedPayload(content="round trip me", memory_type=MemoryType.SEMANTIC),
            source=ProvenanceSource.OBSERVED,
            now=FIXED_NOW,
        )
        (event,) = store.read_stream(user_a)
        assert event.payload == {"content": "round trip me", "memory_type": "semantic"}
        assert event.type is MemoryEventType.INGESTED
        assert event.source is ProvenanceSource.OBSERVED
        assert event.user_id == user_a

    def test_correction_is_a_new_event_not_a_mutation(
        self, store: EventStore, user_a: UserId
    ) -> None:
        original = store.append(
            user_id=user_a,
            payload=IngestedPayload(content="original", memory_type=MemoryType.EPISODIC),
            source=ProvenanceSource.DECLARED,
            now=FIXED_NOW,
        )
        store.append(
            user_id=user_a,
            payload=CorrectedPayload(target_memory_id=MemoryId(original.id), content="corrected"),
            source=ProvenanceSource.DECLARED,
            now=FIXED_NOW,
        )
        stream = store.read_stream(user_a)
        assert len(stream) == 2
        assert stream[0].payload["content"] == "original"
        assert stream[1].type is MemoryEventType.CORRECTED

    def test_read_stream_is_a_fresh_tuple_each_call(
        self, store: EventStore, user_a: UserId
    ) -> None:
        store.append(
            user_id=user_a,
            payload=IngestedPayload(content="x", memory_type=MemoryType.EPISODIC),
            source=ProvenanceSource.DECLARED,
            now=FIXED_NOW,
        )
        first = store.read_stream(user_a)
        second = store.read_stream(user_a)
        assert first == second
