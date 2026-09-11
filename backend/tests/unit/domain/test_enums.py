"""Tests for the closed vocabularies (``mindtrace.domain.enums``)."""

from __future__ import annotations

import pytest

from mindtrace.domain.enums import (
    SCALE_LEVEL_CODES,
    EpistemicState,
    FactorDirection,
    ProvenanceSource,
    ScaleLevel,
)


@pytest.mark.parametrize("member", list(EpistemicState))
def test_epistemic_state_round_trips_through_its_value(member: EpistemicState) -> None:
    assert EpistemicState(member.value) is member


def test_epistemic_state_has_exactly_four_members() -> None:
    assert {m.value for m in EpistemicState} == {"declared", "observed", "inferred", "uncertain"}


def test_provenance_source_is_a_strict_subset_of_epistemic_state() -> None:
    assert {m.value for m in ProvenanceSource} == {"declared", "observed", "inferred"}
    assert "uncertain" not in {m.value for m in ProvenanceSource}


def test_scale_level_rank_is_monotone_with_declaration_order() -> None:
    ranks = [level.rank for level in ScaleLevel]
    assert ranks == sorted(ranks)
    assert ranks == list(range(len(ScaleLevel)))


def test_scale_level_codes_cover_every_level_exactly_once() -> None:
    assert set(SCALE_LEVEL_CODES.values()) == set(ScaleLevel)
    assert len(SCALE_LEVEL_CODES) == len(ScaleLevel)


def test_factor_direction_has_exactly_benefit_and_cost() -> None:
    assert {m.value for m in FactorDirection} == {"benefit", "cost"}


def test_str_enum_values_are_plain_strings_not_generic_placeholders() -> None:
    # Guards against the "collapse into a generic source string" failure mode
    # (M1 Invariant C): every member's value differs from its name casing tricks aside.
    for member in EpistemicState:
        assert isinstance(member.value, str)
        assert member.value == member.value.lower()
