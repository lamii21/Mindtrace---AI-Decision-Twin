"""Tests for the in-memory evidence store (``mindtrace.events.evidence_store``)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from mindtrace.domain.enums import BeliefType, EvidenceSourceKind, Polarity
from mindtrace.domain.evidence import Evidence
from mindtrace.domain.ids import EvidenceId
from mindtrace.events.evidence_store import InMemoryEvidenceStore
from tests.support.memory_fixtures import FIXED_NOW, FIXED_USER, memory_with_evidence_scenario


def _evidence(**overrides: object) -> Evidence:
    defaults: dict[str, object] = {
        "id": EvidenceId(uuid4()),
        "user_id": FIXED_USER,
        "belief_type": BeliefType.PREFERENCE,
        "belief_id": uuid4(),
        "source_kind": EvidenceSourceKind.MEMORY,
        "source_id": uuid4(),
        "weight": 1.0,
        "polarity": Polarity.SUPPORT,
        "engine_version": "m2-fixture",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    defaults.update(overrides)
    return Evidence.model_validate(defaults)


def test_recorded_evidence_is_returned_by_for_belief() -> None:
    store = InMemoryEvidenceStore()
    belief_id = uuid4()
    evidence = _evidence(belief_type=BeliefType.TRAIT, belief_id=belief_id)
    store.record(evidence)

    assert store.for_belief(BeliefType.TRAIT, belief_id) == (evidence,)


def test_for_belief_is_scoped_to_the_exact_belief() -> None:
    store = InMemoryEvidenceStore()
    store.record(_evidence(belief_type=BeliefType.TRAIT, belief_id=uuid4()))
    assert store.for_belief(BeliefType.TRAIT, uuid4()) == ()  # a different, unrecorded belief_id


def test_for_source_finds_the_reverse_direction() -> None:
    store = InMemoryEvidenceStore()
    source_id = uuid4()
    evidence = _evidence(source_kind=EvidenceSourceKind.MEMORY, source_id=source_id)
    store.record(evidence)

    assert store.for_source(EvidenceSourceKind.MEMORY, source_id) == (evidence,)


def test_recording_a_duplicate_id_is_rejected() -> None:
    store = InMemoryEvidenceStore()
    evidence = _evidence()
    store.record(evidence)
    with pytest.raises(ValueError, match="already recorded"):
        store.record(evidence)


def test_store_exposes_no_mutation_or_removal_method() -> None:
    public_methods = {name for name in dir(InMemoryEvidenceStore) if not name.startswith("_")}
    assert public_methods == {"record", "for_belief", "for_source"}


def test_evidence_traces_back_to_its_originating_memory() -> None:
    # The chain the future Evidence Panel walks: belief -> evidence -> source -> memory.
    memory, evidence, store = memory_with_evidence_scenario()

    found = store.for_belief(evidence.belief_type, evidence.belief_id)
    assert found == (evidence,)
    assert found[0].source_kind is EvidenceSourceKind.MEMORY
    assert found[0].source_id == memory.id  # resolves back to the exact memory
    assert found[0].created_at == FIXED_NOW
