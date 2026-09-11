"""Tests for the domain error hierarchy (``mindtrace.domain.errors``)."""

from __future__ import annotations

import pytest

from mindtrace.domain.errors import (
    DomainError,
    MindtraceError,
    SchemaConsistencyError,
    SchemaError,
    SchemaStructureError,
    SchemaValidationError,
)


def test_hierarchy() -> None:
    assert issubclass(DomainError, MindtraceError)
    assert issubclass(SchemaError, DomainError)
    assert issubclass(SchemaStructureError, SchemaError)
    assert issubclass(SchemaValidationError, SchemaError)
    assert issubclass(SchemaConsistencyError, SchemaError)


def test_message_names_source_and_location() -> None:
    err = SchemaValidationError(
        "bad thing", source="factors.yaml", location="factors/alpha/anchors"
    )
    text = str(err)
    assert "factors.yaml" in text
    assert "factors/alpha/anchors" in text
    assert "bad thing" in text


def test_message_without_location_is_still_actionable() -> None:
    err = SchemaError("something went wrong", source="traits.yaml")
    assert str(err) == "traits.yaml: something went wrong"


def test_message_without_source_falls_back_to_a_label() -> None:
    err = SchemaError("something went wrong")
    assert str(err) == "schema: something went wrong"


def test_is_a_real_exception_type() -> None:
    with pytest.raises(SchemaValidationError):
        raise SchemaValidationError("x", source="y")
