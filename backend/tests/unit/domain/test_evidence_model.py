"""Tests for the ``Evidence`` provenance-edge type (``mindtrace.domain.evidence``)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mindtrace.domain.enums import BeliefType, EvidenceSourceKind, Polarity
from mindtrace.domain.evidence import Evidence
from tests.support.memory_fixtures import memory_with_evidence_scenario


def test_evidence_points_from_a_belief_to_a_source() -> None:
    memory, evidence, _store = memory_with_evidence_scenario()
    assert evidence.belief_type is BeliefType.DECISION_FACTOR
    assert evidence.source_kind is EvidenceSourceKind.MEMORY
    assert evidence.source_id == memory.id
    assert evidence.polarity is Polarity.SUPPORT


def test_evidence_is_frozen() -> None:
    _memory, evidence, _store = memory_with_evidence_scenario()
    with pytest.raises(ValidationError):
        evidence.weight = 0.5


def test_extra_field_rejected() -> None:
    _memory, evidence, _store = memory_with_evidence_scenario()
    data = evidence.model_dump(mode="json")
    data["not_a_real_field"] = True
    with pytest.raises(ValidationError):
        Evidence.model_validate(data)


def test_serialisation_round_trip_preserves_every_field() -> None:
    _memory, evidence, _store = memory_with_evidence_scenario()
    dumped = evidence.model_dump(mode="json")
    restored = Evidence.model_validate(dumped)
    assert restored == evidence


def test_belief_type_and_source_kind_are_real_enums() -> None:
    _memory, evidence, _store = memory_with_evidence_scenario()
    assert isinstance(evidence.belief_type, BeliefType)
    assert isinstance(evidence.source_kind, EvidenceSourceKind)
    bad = evidence.model_dump(mode="json") | {"belief_type": "not_a_belief_type"}
    with pytest.raises(ValidationError):
        Evidence.model_validate(bad)
