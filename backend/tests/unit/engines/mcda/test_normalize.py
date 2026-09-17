"""Direct unit tests for the pure functions in `mindtrace.engines.mcda.normalize`.

`decide()` always calls these with a `WeightVector` that covers every core
factor (its own validator forbids anything else), so exercising the "factor
absent from the weight map" branches - legal for these functions in isolation,
just never reachable through `decide()` - needs to happen here, directly.
"""

from __future__ import annotations

import math

from tests.support.mcda_fixtures import TAXONOMY

from mindtrace.domain.decision import DispositionInputs
from mindtrace.domain.enums import FactorDirection
from mindtrace.domain.ids import FactorId
from mindtrace.engines.mcda.config import DEFAULT_MCDA_CONFIG
from mindtrace.engines.mcda.normalize import (
    adjust_weights,
    curve_exponent,
    normalize_factor,
    renormalize_known,
)

_NEUTRAL = DispositionInputs.neutral()


class TestCurveExponent:
    def test_neutral_dispositions_give_gamma_one_for_a_risk_curve_factor(self) -> None:
        gamma = curve_exponent(FactorId("downside_risk"), _NEUTRAL, DEFAULT_MCDA_CONFIG)
        assert math.isclose(gamma, 1.0)

    def test_neutral_dispositions_give_gamma_one_for_the_effort_curve_factor(self) -> None:
        gamma = curve_exponent(FactorId("time_demand"), _NEUTRAL, DEFAULT_MCDA_CONFIG)
        assert math.isclose(gamma, 1.0)

    def test_a_factor_with_no_curve_always_has_gamma_one(self) -> None:
        extreme = DispositionInputs(
            risk_tolerance=0.0, time_discount=0.0, ambiguity_aversion=0.0, effort_tolerance=0.0
        )
        gamma = curve_exponent(FactorId("skill_growth"), extreme, DEFAULT_MCDA_CONFIG)
        assert gamma == 1.0

    def test_low_risk_tolerance_bends_the_risk_curve_away_from_one(self) -> None:
        low_tolerance = DispositionInputs(
            risk_tolerance=0.0, time_discount=0.5, ambiguity_aversion=0.5, effort_tolerance=0.5
        )
        gamma = curve_exponent(FactorId("downside_risk"), low_tolerance, DEFAULT_MCDA_CONFIG)
        assert not math.isclose(gamma, 1.0)


class TestNormalizeFactor:
    def test_benefit_factor_normalizes_to_its_shaped_anchor(self) -> None:
        spec = TAXONOMY.get("skill_growth")
        assert spec.direction is FactorDirection.BENEFIT
        anchor = spec.anchor_for(spec.range_max)
        result = normalize_factor(spec, anchor, _NEUTRAL, DEFAULT_MCDA_CONFIG)
        assert math.isclose(result, anchor)

    def test_cost_factor_normalizes_to_one_minus_its_shaped_anchor(self) -> None:
        spec = TAXONOMY.get("downside_risk")
        assert spec.direction is FactorDirection.COST
        anchor = spec.anchor_for(spec.range_max)
        result = normalize_factor(spec, anchor, _NEUTRAL, DEFAULT_MCDA_CONFIG)
        assert math.isclose(result, 1.0 - anchor)


class TestAdjustWeights:
    def test_time_discount_weight_slope_shrinks_time_discount_factors(self) -> None:
        raw = {FactorId("option_value"): 0.5, FactorId("skill_growth"): 0.5}
        high_discount = DispositionInputs(
            risk_tolerance=0.5, time_discount=1.0, ambiguity_aversion=0.5, effort_tolerance=0.5
        )
        adjusted = adjust_weights(raw, high_discount, DEFAULT_MCDA_CONFIG)
        assert adjusted[FactorId("option_value")] < raw[FactorId("option_value")]
        assert adjusted[FactorId("skill_growth")] == raw[FactorId("skill_growth")]

    def test_ambiguity_bump_applies_only_when_reversibility_is_present(self) -> None:
        raw = {FactorId("skill_growth"): 1.0}  # no "reversibility" key at all
        high_ambiguity = DispositionInputs(
            risk_tolerance=0.5, time_discount=0.5, ambiguity_aversion=1.0, effort_tolerance=0.5
        )
        adjusted = adjust_weights(raw, high_ambiguity, DEFAULT_MCDA_CONFIG)
        assert adjusted == raw

    def test_ambiguity_bump_grows_reversibility_weight_with_ambiguity_aversion(self) -> None:
        raw = {FactorId("reversibility"): 0.5, FactorId("skill_growth"): 0.5}
        high_ambiguity = DispositionInputs(
            risk_tolerance=0.5, time_discount=0.5, ambiguity_aversion=1.0, effort_tolerance=0.5
        )
        adjusted = adjust_weights(raw, high_ambiguity, DEFAULT_MCDA_CONFIG)
        assert adjusted[FactorId("reversibility")] > raw[FactorId("reversibility")]


class TestRenormalizeKnown:
    def test_typical_case_renormalizes_to_sum_one_and_reports_coverage(self) -> None:
        adjusted = {FactorId("skill_growth"): 0.6, FactorId("autonomy"): 0.4}
        known = (FactorId("skill_growth"),)
        weights, coverage = renormalize_known(adjusted, known)
        assert math.isclose(weights[FactorId("skill_growth")], 1.0)
        assert math.isclose(coverage, 0.6)

    def test_empty_known_set_yields_zero_coverage_and_no_weights(self) -> None:
        adjusted = {FactorId("skill_growth"): 0.6, FactorId("autonomy"): 0.4}
        weights, coverage = renormalize_known(adjusted, ())
        assert weights == {}
        assert coverage == 0.0

    def test_known_subset_with_zero_total_weight_yields_zero_coverage_and_zero_weights(
        self,
    ) -> None:
        adjusted = {FactorId("skill_growth"): 0.0, FactorId("autonomy"): 1.0}
        known = (FactorId("skill_growth"),)
        weights, coverage = renormalize_known(adjusted, known)
        assert weights == {FactorId("skill_growth"): 0.0}
        assert coverage == 0.0
