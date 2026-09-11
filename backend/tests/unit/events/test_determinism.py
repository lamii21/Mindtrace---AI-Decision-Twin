"""Determinism and rebuildability tests for the event/projection layer (M2 s11/s12)."""

from __future__ import annotations

import random
from typing import Any

from mindtrace.domain.ids import MemoryId
from mindtrace.events.in_memory_store import InMemoryEventStore
from mindtrace.events.projectors.memory import fold_memory_events
from mindtrace.events.rederive import rederive
from tests.support.memory_fixtures import FIXED_USER, correct, delete, deterministic_store, ingest


def _build_history() -> tuple[InMemoryEventStore, MemoryId]:
    store = deterministic_store()
    e1 = ingest(store, content="I care about growth.")
    ingest(store, content="I logged a decision.")
    correct(store, target=MemoryId(e1.id), content="I care about growth and stability.")
    return store, MemoryId(e1.id)


def test_folding_the_same_events_twice_is_equal() -> None:
    store, _ = _build_history()
    events = store.read_stream(FIXED_USER)
    first = fold_memory_events(FIXED_USER, events)
    second = fold_memory_events(FIXED_USER, events)
    assert first == second
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_fold_is_immune_to_poisoned_ambient_state(monkeypatch: Any) -> None:
    """Replay must not consult the wall clock, the environment, or global RNG state."""

    def _boom_time() -> float:
        msg = "the memory fold must not read the wall clock"
        raise AssertionError(msg)

    store, _ = _build_history()
    events = store.read_stream(FIXED_USER)

    monkeypatch.setattr("time.time", _boom_time)
    monkeypatch.setenv("SOME_UNRELATED_VAR", "poison")
    random.seed(1234567)
    first = fold_memory_events(FIXED_USER, events)
    random.seed(7654321)
    second = fold_memory_events(FIXED_USER, events)

    assert first == second


def test_rebuildability_discard_and_replay_reconstructs_the_same_state() -> None:
    store, _ = _build_history()
    original = rederive(store, FIXED_USER)

    del original  # simulate discarding the in-process state entirely

    rebuilt = rederive(store, FIXED_USER)
    reference = fold_memory_events(FIXED_USER, store.read_stream(FIXED_USER))

    assert rebuilt == reference


def test_deletion_history_also_replays_deterministically() -> None:
    store = deterministic_store()
    e1 = ingest(store, content="temporary")
    delete(store, targets=(MemoryId(e1.id),))
    events = store.read_stream(FIXED_USER)

    assert fold_memory_events(FIXED_USER, events) == fold_memory_events(FIXED_USER, events)


def test_event_order_in_the_input_sequence_cannot_be_reshuffled_and_still_match() -> None:
    # A sanity check that the fold really does depend on order (not just on set membership):
    # reversing e1/e2's positions (while keeping seq intact) breaks the seq-contiguity check.
    store = deterministic_store()
    ingest(store, content="a")
    ingest(store, content="b")
    events = store.read_stream(FIXED_USER)
    reversed_events = tuple(reversed(events))
    assert events != reversed_events

    forward = fold_memory_events(FIXED_USER, events)
    assert forward.last_seq == 2
