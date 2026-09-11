"""Tests for the ``Memory`` projection type (``mindtrace.domain.memory``)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from mindtrace.domain.enums import MemoryType, ProvenanceSource
from mindtrace.domain.memory import Memory
from tests.support.memory_fixtures import (
    declared_memory_example,
    inferred_memory_example,
    observed_memory_example,
)


def test_declared_example_is_current_and_has_no_termination() -> None:
    memory = declared_memory_example()
    assert memory.source is ProvenanceSource.DECLARED
    assert memory.is_current
    assert memory.superseded_by is None
    assert memory.deleted_at is None
    assert memory.deleted_by_event_seq is None


def test_observed_example_carries_an_occurred_at_date() -> None:
    memory = observed_memory_example()
    assert memory.source is ProvenanceSource.OBSERVED
    assert isinstance(memory.occurred_at, date)


def test_inferred_example_is_a_real_source_value() -> None:
    memory = inferred_memory_example()
    assert memory.source is ProvenanceSource.INFERRED
    assert memory.is_current


def test_is_current_false_once_superseded() -> None:
    memory = declared_memory_example()
    superseded = memory.model_copy(update={"superseded_by": declared_memory_example().id})
    assert not superseded.is_current


def test_is_current_false_once_deleted() -> None:
    memory = declared_memory_example()
    deleted = memory.model_copy(
        update={"deleted_at": datetime(2026, 1, 1, tzinfo=UTC), "deleted_by_event_seq": 5}
    )
    assert not deleted.is_current


def test_memory_is_frozen() -> None:
    memory = declared_memory_example()
    with pytest.raises(ValidationError):
        memory.content = "changed"


def test_extra_field_rejected() -> None:
    data = declared_memory_example().model_dump(mode="json")
    data["not_a_real_field"] = 123
    with pytest.raises(ValidationError):
        Memory.model_validate(data)


def test_serialisation_round_trip_preserves_every_field() -> None:
    memory = observed_memory_example()
    dumped = memory.model_dump(mode="json")
    restored = Memory.model_validate(dumped)
    assert restored == memory


def test_memory_type_is_a_real_enum_not_a_string() -> None:
    memory = declared_memory_example()
    assert isinstance(memory.type, MemoryType)
    bad = memory.model_dump(mode="json") | {"type": "not_a_type"}
    with pytest.raises(ValidationError):
        Memory.model_validate(bad)
