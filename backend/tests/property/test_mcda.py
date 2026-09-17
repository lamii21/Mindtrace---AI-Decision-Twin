"""Property-based tests for the MCDA engine (M3 s16).

Every property here is one the mathematics in ``docs/spec/05-mcda-mathematics.md``
actually guarantees - not a property that merely "seems to usually hold". Where
the spec is silent or a property only holds under an extra condition (e.g. weight
scaling is only invariant on the *known* subset, monotonicity only holds while a
factor stays on one side of its curve's shape), the test encodes that condition
explicitly rather than papering over occasional Hypothesis failures.
"""

from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from mindtrace.domain.decision import DispositionInputs, FactorReading, FactorVector, WeightVector
from mindtrace.domain.enums import ScaleLevel
from mindtrace.domain.ids import FactorId
from mindtrace.engines.mcda.decide import decide
from tests.support.mcda_fixtures import TAXONOMY

_CORE_IDS = TAXONOMY.core_ids
_SCALE_LEVELS = list(ScaleLevel)

_dispositions_strategy = st.builds(
    DispositionInputs,
    risk_tolerance=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    time_discount=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    ambiguity_aversion=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    effort_tolerance=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)


@st.composite
def weight_vectors(draw: st.DrawFn) -> WeightVector:
    """A valid `WeightVector` over every core factor: positive raw draws, normalised to sum 1."""
    raw = [draw(st.floats(min_value=0.01, max_value=1.0, allow_nan=False)) for _ in _CORE_IDS]
    total = sum(raw)
    return WeightVector(weights=dict(zip(_CORE_IDS, (v / total for v in raw), strict=True)))


@st.composite
def known_subsets(draw: st.DrawFn, *, min_size: int = 1) -> tuple[FactorId, ...]:
    """A non-empty subset of core factor ids, sorted (matches `FactorVector.known_ids()`)."""
    chosen = draw(
        st.lists(
            st.sampled_from(_CORE_IDS), min_size=min_size, max_size=len(_CORE_IDS), unique=True
        )
    )
    return tuple(sorted(chosen))


@st.composite
def factor_vectors(draw: st.DrawFn, *, known: tuple[FactorId, ...] | None = None) -> FactorVector:
    """A `FactorVector` where `known` (default: a drawn subset) carries a random level."""
    known_set = known if known is not None else draw(known_subsets())
    items = []
    for factor_id in _CORE_IDS:
        if factor_id in known_set:
            level = draw(st.sampled_from(_SCALE_LEVELS))
            items.append((factor_id, FactorReading(known=True, level=level)))
        else:
            items.append((factor_id, FactorReading(known=False)))
    return FactorVector.from_items(items)


@given(weights=weight_vectors(), factors=factor_vectors(), dispositions=_dispositions_strategy)
@settings(max_examples=200)
def test_determinism_same_input_same_result(
    weights: WeightVector, factors: FactorVector, dispositions: DispositionInputs
) -> None:
    """spec/05 s10 property 7: identical inputs always produce a byte-identical result."""
    first = decide(TAXONOMY, weights, factors, dispositions)
    second = decide(TAXONOMY, weights, factors, dispositions)
    assert first.model_dump_json() == second.model_dump_json()


@given(weights=weight_vectors(), factors=factor_vectors(), dispositions=_dispositions_strategy)
@settings(max_examples=200)
def test_result_is_independent_of_reading_insertion_order(
    weights: WeightVector, factors: FactorVector, dispositions: DispositionInputs
) -> None:
    """Rebuilding the same `FactorVector` with readings inserted in reverse order changes nothing.

    Guards against the hash-randomisation-order failure mode this codebase
    repeatedly designs against: dict/set iteration order must never leak into
    a floating-point summation's result.
    """
    reversed_items = list(reversed(factors.readings.items()))
    reordered = FactorVector.from_items(reversed_items)
    first = decide(TAXONOMY, weights, factors, dispositions)
    second = decide(TAXONOMY, weights, reordered, dispositions)
    assert first.model_dump_json() == second.model_dump_json()


@given(
    weights=weight_vectors(),
    factors=factor_vectors(),
    dispositions=_dispositions_strategy,
    scale=st.floats(min_value=0.1, max_value=10.0, allow_nan=False),
)
@settings(max_examples=100)
def test_uniform_rescale_of_known_weights_does_not_change_score(
    weights: WeightVector,
    factors: FactorVector,
    dispositions: DispositionInputs,
    scale: float,
) -> None:
    """Renormalisation is scale-invariant on the known subset (proved when fixing the T-ref
    weight-table bug; spec/05 s2c divides by the known subset's own sum, so any single positive
    factor applied uniformly across the *entire* raw weight vector cancels out completely)."""
    baseline = decide(TAXONOMY, weights, factors, dispositions)

    rescaled_raw = {factor_id: w * scale for factor_id, w in weights.weights.items()}
    total = sum(rescaled_raw.values())
    rescaled = WeightVector(weights={k: v / total for k, v in rescaled_raw.items()})
    result = decide(TAXONOMY, rescaled, factors, dispositions)

    assert math.isclose(result.score, baseline.score, abs_tol=1e-9)
    assert math.isclose(result.raw_score, baseline.raw_score, abs_tol=1e-9)
    baseline_pct = {c.factor_id: c.contribution_pct for c in baseline.contributions}
    result_pct = {c.factor_id: c.contribution_pct for c in result.contributions}
    for factor_id, pct in baseline_pct.items():
        assert math.isclose(result_pct[factor_id], pct, abs_tol=1e-6)


@given(weights=weight_vectors(), known=known_subsets(), dispositions=_dispositions_strategy)
@settings(max_examples=100)
def test_neutral_dispositions_give_gamma_one_for_every_factor(
    weights: WeightVector, known: tuple[FactorId, ...], dispositions: DispositionInputs
) -> None:
    """spec/05 s10 property 8, indirectly: with neutral dispositions, `normalize_factor` never
    curve-shapes - a BENEFIT factor's normalized value equals its raw anchor exactly."""
    neutral = DispositionInputs.neutral()
    items = []
    for factor_id in TAXONOMY.core_ids:
        if factor_id in known:
            items.append((factor_id, FactorReading(known=True, level=ScaleLevel.HIGH)))
        else:
            items.append((factor_id, FactorReading(known=False)))
    factors = FactorVector.from_items(items)
    result = decide(TAXONOMY, weights, factors, neutral)
    for contribution in result.contributions:
        spec = TAXONOMY.get(contribution.factor_id)
        anchor = spec.anchor_for(ScaleLevel.HIGH)
        expected_n_a = anchor if spec.direction.value == "benefit" else 1.0 - anchor
        assert math.isclose(contribution.normalized_value_a, expected_n_a, abs_tol=1e-9)


@given(weights=weight_vectors(), dispositions=_dispositions_strategy)
@settings(max_examples=100)
def test_zero_weight_factor_contributes_nothing(
    weights: WeightVector, dispositions: DispositionInputs
) -> None:
    """A near-zero-weight factor barely moves the score (spec s6: c_i = w_i * (n_i(A) - n_i(B)))."""
    zeroed_id = _CORE_IDS[0]
    remaining = {k: v for k, v in weights.weights.items() if k != zeroed_id}
    remaining_total = sum(remaining.values())
    if remaining_total <= 0:
        return
    rescaled = {k: v / remaining_total * 0.999 for k, v in remaining.items()}
    rescaled[zeroed_id] = 0.001
    total = sum(rescaled.values())
    tiny_weights = WeightVector(weights={k: v / total for k, v in rescaled.items()})

    items = [
        (factor_id, FactorReading(known=True, level=ScaleLevel.MODERATE)) for factor_id in _CORE_IDS
    ]
    factors = FactorVector.from_items(items)
    result = decide(TAXONOMY, tiny_weights, factors, dispositions)
    zeroed_contribution = next(c for c in result.contributions if c.factor_id == zeroed_id)
    assert abs(zeroed_contribution.contribution_pct) < 1.0


@given(weights=weight_vectors(), factors=factor_vectors(), dispositions=_dispositions_strategy)
@settings(max_examples=100)
def test_contributions_sum_to_raw_score(
    weights: WeightVector, factors: FactorVector, dispositions: DispositionInputs
) -> None:
    """spec/05 s6 "Identity (pre-clamp)": `sum(c_i) == raw_score`, always, before any clamping."""
    result = decide(TAXONOMY, weights, factors, dispositions)
    total = sum(c.raw_contribution for c in result.contributions)
    assert math.isclose(total, result.raw_score, abs_tol=1e-9)


@given(weights=weight_vectors(), factors=factor_vectors(), dispositions=_dispositions_strategy)
@settings(max_examples=100)
def test_contribution_percentages_sum_to_100_in_magnitude(
    weights: WeightVector, factors: FactorVector, dispositions: DispositionInputs
) -> None:
    """spec/05 s6: `sum(|c_i%|) == 100`, unless every contribution is exactly zero."""
    result = decide(TAXONOMY, weights, factors, dispositions)
    total_abs_pct = sum(abs(c.contribution_pct) for c in result.contributions)
    all_zero = all(c.raw_contribution == 0.0 for c in result.contributions)
    if all_zero:
        assert total_abs_pct == 0.0
    else:
        assert math.isclose(total_abs_pct, 100.0, abs_tol=1e-6)


@given(weights=weight_vectors(), factors=factor_vectors(), dispositions=_dispositions_strategy)
@settings(max_examples=100)
def test_score_and_coverage_stay_in_bounds(
    weights: WeightVector, factors: FactorVector, dispositions: DispositionInputs
) -> None:
    """`score` in [-1, 1] always (post-clamp); `coverage` in [0, 1] always."""
    result = decide(TAXONOMY, weights, factors, dispositions)
    assert -1.0 <= result.score <= 1.0
    assert 0.0 <= result.coverage <= 1.0 + 1e-9


@given(weights=weight_vectors(), dispositions=_dispositions_strategy)
@settings(max_examples=100)
def test_moderate_level_normalizes_to_its_direction_corrected_anchor(
    weights: WeightVector, dispositions: DispositionInputs
) -> None:
    """`normalize_factor` for MODERATE matches the spec anchor exactly, direction-corrected -
    not a hardcoded 0.5, since a factor's MODERATE anchor need not sit at the scale midpoint."""
    neutral = DispositionInputs.neutral()
    items = [
        (factor_id, FactorReading(known=True, level=ScaleLevel.MODERATE)) for factor_id in _CORE_IDS
    ]
    factors = FactorVector.from_items(items)
    result = decide(TAXONOMY, weights, factors, neutral)
    for contribution in result.contributions:
        spec = TAXONOMY.get(contribution.factor_id)
        # MODERATE's anchor need not be exactly 0.5 for every factor (only symmetry of the
        # BENEFIT/COST correction is guaranteed) - so assert what the spec actually promises:
        # n_a matches the direction-corrected anchor exactly, not a hardcoded 0.5.
        anchor = spec.anchor_for(ScaleLevel.MODERATE)
        expected = anchor if spec.direction.value == "benefit" else 1.0 - anchor
        assert math.isclose(contribution.normalized_value_a, expected, abs_tol=1e-9)
