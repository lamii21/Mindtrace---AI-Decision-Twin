"""Property-based tests for factor taxonomy parsing (``docs/09-testing-strategy.md`` s1).

These exercise the invariants ``docs/spec/05-mcda-mathematics.md`` s10 ultimately
depends on: a monotone anchor curve is accepted and preserved exactly; a
non-monotone one is always rejected; and parsing is invariant to the order
factors are declared in.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from mindtrace.domain.enums import ScaleLevel
from mindtrace.domain.errors import SchemaValidationError
from mindtrace.domain.factors import parse_factor_taxonomy
from tests.support.schema_factories import deep_copy, minimal_factors_dict

_LEVELS = list(ScaleLevel)

# Five distinct floats in [0, 1], later sorted -> a valid strictly-increasing anchor curve.
_five_distinct_unit_floats = st.lists(
    st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    min_size=5,
    max_size=5,
    unique=True,
)


@given(values=_five_distinct_unit_floats)
def test_strictly_increasing_anchor_curve_is_accepted_and_preserved(values: list[float]) -> None:
    ordered = sorted(values)
    data = deep_copy(minimal_factors_dict())
    data["factors"][0]["anchors"] = dict(zip((lvl.value for lvl in _LEVELS), ordered, strict=True))

    taxonomy = parse_factor_taxonomy(data)

    parsed_factor = taxonomy.get("alpha")
    for level, expected in zip(_LEVELS, ordered, strict=True):
        assert parsed_factor.anchor_for(level) == expected


@given(values=_five_distinct_unit_floats)
def test_reversed_anchor_curve_is_always_rejected(values: list[float]) -> None:
    # `unique=True` guarantees 5 distinct values, so sorting descending is always strictly
    # decreasing - never accidentally equal to the increasing order.
    reversed_curve = sorted(values, reverse=True)
    data = deep_copy(minimal_factors_dict())
    level_values = (lvl.value for lvl in _LEVELS)
    data["factors"][0]["anchors"] = dict(zip(level_values, reversed_curve, strict=True))

    with pytest.raises(SchemaValidationError, match="strictly increase"):
        parse_factor_taxonomy(data)


@given(order=st.permutations([0, 1, 2]))
def test_parsing_is_invariant_to_factor_declaration_order(order: tuple[int, int, int]) -> None:
    data = deep_copy(minimal_factors_dict())
    all_factors = [*data["factors"], *data["extended_factors"]]
    reordered = [all_factors[i] for i in order]
    reordered_core = [f for f in reordered if f["id"] in {"alpha", "beta"}]
    reordered_extended = [f for f in reordered if f["id"] == "gamma"]
    data["factors"] = reordered_core
    data["extended_factors"] = reordered_extended

    taxonomy = parse_factor_taxonomy(data)

    assert taxonomy.all_ids == frozenset({"alpha", "beta", "gamma"})
    assert taxonomy.get("alpha").direction.value == "benefit"
    assert taxonomy.get("beta").direction.value == "cost"
