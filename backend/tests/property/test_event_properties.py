"""Property-based tests for the event/projection layer (M2 s16).

Each property targets something the example-based tests in ``tests/unit/events/``
can only sample: that *any* valid history replays deterministically, that
order (not just event membership) is what the fold checks, and that every
event type round-trips through JSON with nothing lost.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st

from mindtrace.domain.enums import MemoryType, ProvenanceSource
from mindtrace.domain.errors import DomainError
from mindtrace.domain.ids import EventId, MemoryId
from mindtrace.events.enums import MemoryEventType
from mindtrace.events.projectors.memory import fold_memory_events
from mindtrace.events.types import CorrectedPayload, DeletedPayload, Event, IngestedPayload
from tests.support.memory_fixtures import FIXED_USER, deterministic_store, ingest

_short_text = st.text(min_size=1, max_size=40).filter(lambda s: s.strip() != "")
_memory_type = st.sampled_from(list(MemoryType))


@dataclass(frozen=True)
class _Ingest:
    content: str


@dataclass(frozen=True)
class _Correct:
    target_slot: int
    content: str


@dataclass(frozen=True)
class _Delete:
    target_slot: int


_Op = _Ingest | _Correct | _Delete


@st.composite
def valid_event_programs(draw: st.DrawFn, max_ops: int = 8) -> list[_Op]:
    """A valid op sequence: ``correct``/``delete`` only ever target a currently-live slot."""
    ops: list[_Op] = []
    live_slots: list[int] = []
    n = draw(st.integers(min_value=1, max_value=max_ops))
    kinds = st.sampled_from(["ingest", "correct", "delete"])
    for _ in range(n):
        kind = draw(kinds if live_slots else st.just("ingest"))
        if kind == "ingest":
            ops.append(_Ingest(draw(_short_text)))
            live_slots.append(len(ops) - 1)
        elif kind == "correct":
            target = draw(st.sampled_from(live_slots))
            ops.append(_Correct(target, draw(_short_text)))
            live_slots.remove(target)
            live_slots.append(len(ops) - 1)
        else:
            target = draw(st.sampled_from(live_slots))
            ops.append(_Delete(target))
            live_slots.remove(target)
    return ops


@given(ops=valid_event_programs())
def test_any_valid_history_folds_deterministically(ops: list[_Op]) -> None:
    store = deterministic_store()
    slot_to_memory_id: dict[int, MemoryId] = {}
    fixed_now = datetime(2026, 1, 1, tzinfo=UTC)

    for index, op in enumerate(ops):
        if isinstance(op, _Ingest):
            event = ingest(store, content=op.content)
        elif isinstance(op, _Correct):
            event = store.append(
                user_id=FIXED_USER,
                payload=CorrectedPayload(
                    target_memory_id=slot_to_memory_id[op.target_slot], content=op.content
                ),
                source=ProvenanceSource.DECLARED,
                now=fixed_now,
            )
        else:
            event = store.append(
                user_id=FIXED_USER,
                payload=DeletedPayload(target_memory_ids=(slot_to_memory_id[op.target_slot],)),
                source=ProvenanceSource.DECLARED,
                now=fixed_now,
            )
        slot_to_memory_id[index] = MemoryId(event.id)

    events = store.read_stream(FIXED_USER)
    first = fold_memory_events(FIXED_USER, events)
    second = fold_memory_events(FIXED_USER, events)

    assert first == second
    # ingest and correct each mint a new row; delete tombstones an existing one in place.
    expected_rows = sum(1 for op in ops if isinstance(op, _Ingest | _Correct))
    assert len(first.memories) == expected_rows
    assert first.last_seq == len(events)
    assert [e.seq for e in events] == list(range(1, len(events) + 1))


@given(seqs=st.permutations(range(1, 6)).filter(lambda p: list(p) != list(range(1, 6))))
def test_any_non_identity_seq_ordering_is_rejected(seqs: tuple[int, ...]) -> None:
    events = tuple(
        Event(
            id=EventId(uuid4()),
            user_id=FIXED_USER,
            seq=seq,
            type=MemoryEventType.INGESTED,
            payload=IngestedPayload(
                content=f"item {i}", memory_type=MemoryType.EPISODIC
            ).model_dump(mode="json"),
            source=ProvenanceSource.DECLARED,
            occurred_at=None,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        for i, seq in enumerate(seqs)
    )
    with pytest.raises(DomainError):
        fold_memory_events(FIXED_USER, events)


@given(content=_short_text, memory_type=_memory_type)
def test_ingested_payload_round_trips_through_json(content: str, memory_type: MemoryType) -> None:
    payload = IngestedPayload(content=content, memory_type=memory_type)
    restored = IngestedPayload.model_validate(payload.model_dump(mode="json"))
    assert restored == payload


@given(content=_short_text)
def test_corrected_payload_round_trips_through_json(content: str) -> None:
    payload = CorrectedPayload(target_memory_id=MemoryId(uuid4()), content=content)
    restored = CorrectedPayload.model_validate(payload.model_dump(mode="json"))
    assert restored == payload


@given(n_targets=st.integers(min_value=1, max_value=5))
def test_deleted_payload_round_trips_through_json(n_targets: int) -> None:
    payload = DeletedPayload(target_memory_ids=tuple(MemoryId(uuid4()) for _ in range(n_targets)))
    restored = DeletedPayload.model_validate(payload.model_dump(mode="json"))
    assert restored == payload
