"""Validation, baseline/described-B, and `decide_multi_option` (spec §8).

The golden tests in ``tests/golden/test_mcda_golden.py`` exercise ``decide``'s
five worked-example happy paths; this module covers the paths those examples
never touch: rejected inputs, an explicitly described ``B``, and the
multi-option ranking entry point.
"""

from __future__ import annotations

import math
from typing import ClassVar

import pytest
from tests.support.mcda_fixtures import T_REF_DISPOSITIONS, T_REF_WEIGHTS, TAXONOMY, factor_vector

from mindtrace.domain.decision import DispositionInputs, FactorReading, FactorVector, WeightVector
from mindtrace.domain.enums import DecisionOutcome, ScaleLevel
from mindtrace.domain.ids import FactorId
from mindtrace.engines.mcda.decide import decide, decide_multi_option
from mindtrace.engines.mcda.errors import MCDAValidationError

_NEUTRAL = DispositionInputs.neutral()


class TestWeightValidation:
    def test_weights_missing_a_core_factor_are_rejected(self) -> None:
        incomplete = {k: v for k, v in T_REF_WEIGHTS.weights.items() if k != "reversibility"}
        total = sum(incomplete.values())
        weights = WeightVector(weights={k: v / total for k, v in incomplete.items()})
        factors = factor_vector({"skill_growth": "high"})
        with pytest.raises(MCDAValidationError, match="missing="):
            decide(TAXONOMY, weights, factors, _NEUTRAL)

    def test_weights_with_an_extra_non_taxonomy_factor_are_rejected(self) -> None:
        extra = dict(T_REF_WEIGHTS.weights)
        bogus_id = FactorId("not_a_real_factor")
        extra[bogus_id] = 0.0
        weights = WeightVector(weights=extra)
        factors = factor_vector({"skill_growth": "high"})
        with pytest.raises(MCDAValidationError, match="extra="):
            decide(TAXONOMY, weights, factors, _NEUTRAL)


class TestFactorVectorValidation:
    def test_factor_vector_referencing_unknown_id_is_rejected(self) -> None:
        factors = FactorVector.from_items(
            [(FactorId("not_a_real_factor"), FactorReading(known=True, level=ScaleLevel.HIGH))]
        )
        with pytest.raises(MCDAValidationError, match="outside the taxonomy"):
            decide(TAXONOMY, T_REF_WEIGHTS, factors, _NEUTRAL)

    def test_factor_vector_referencing_extended_factor_is_rejected(self) -> None:
        factors = FactorVector.from_items(
            [(FactorId("novelty"), FactorReading(known=True, level=ScaleLevel.HIGH))]
        )
        with pytest.raises(MCDAValidationError, match="non-core"):
            decide(TAXONOMY, T_REF_WEIGHTS, factors, _NEUTRAL)


class TestBaselineVsDescribedB:
    def test_default_baseline_uses_config_baseline_n_for_every_known_factor(self) -> None:
        factors = factor_vector({"skill_growth": "high"})
        result = decide(TAXONOMY, T_REF_WEIGHTS, factors, _NEUTRAL)
        contribution = result.contributions[0]
        assert contribution.normalized_value_b == 0.5

    def test_described_b_overrides_baseline_for_factors_it_covers(self) -> None:
        factors_a = factor_vector({"skill_growth": "very_high"})
        factors_b = factor_vector({"skill_growth": "low"})
        result = decide(TAXONOMY, T_REF_WEIGHTS, factors_a, _NEUTRAL, factors_b=factors_b)
        contribution = result.contributions[0]
        spec = TAXONOMY.get("skill_growth")
        assert math.isclose(contribution.normalized_value_b, spec.anchor_for(ScaleLevel.LOW))

    def test_described_b_falls_back_to_baseline_for_factors_it_does_not_cover(self) -> None:
        factors_a = factor_vector({"skill_growth": "high", "autonomy": "high"})
        factors_b = factor_vector({"skill_growth": "low"})  # silent on autonomy
        result = decide(TAXONOMY, T_REF_WEIGHTS, factors_a, _NEUTRAL, factors_b=factors_b)
        autonomy = next(c for c in result.contributions if c.factor_id == "autonomy")
        assert autonomy.normalized_value_b == 0.5


_MULTI_OPTION_FACTORS = {
    "startup": {
        "skill_growth": "very_high",
        "financial_return": "low",
        "financial_security": "low",
        "downside_risk": "high",
        "location_fit": "moderate",
        "intrinsic_interest": "very_high",
    },
    "bigco": {
        "skill_growth": "moderate",
        "financial_return": "very_high",
        "financial_security": "very_high",
        "downside_risk": "very_low",
        "location_fit": "high",
        "intrinsic_interest": "moderate",
    },
    "freelance": {
        "skill_growth": "low",
        "financial_return": "moderate",
        "financial_security": "very_low",
        "downside_risk": "very_high",
        "location_fit": "low",
        "intrinsic_interest": "low",
    },
}


class TestDecideMultiOption:
    _OPTIONS: ClassVar = [
        (label, factor_vector(levels)) for label, levels in _MULTI_OPTION_FACTORS.items()
    ]

    def test_fewer_than_three_options_is_rejected(self) -> None:
        with pytest.raises(MCDAValidationError, match=">= 3"):
            decide_multi_option(TAXONOMY, T_REF_WEIGHTS, self._OPTIONS[:2], T_REF_DISPOSITIONS)

    def test_options_with_different_known_sets_are_rejected(self) -> None:
        mismatched = [
            *self._OPTIONS[:2],
            ("odd_one_out", factor_vector({"skill_growth": "high"})),
        ]
        with pytest.raises(MCDAValidationError, match="different known-factor set"):
            decide_multi_option(TAXONOMY, T_REF_WEIGHTS, mismatched, T_REF_DISPOSITIONS)

    def test_picks_the_highest_scoring_option_as_selected(self) -> None:
        result = decide_multi_option(TAXONOMY, T_REF_WEIGHTS, self._OPTIONS, T_REF_DISPOSITIONS)
        assert result.label is DecisionOutcome.ACCEPT
        assert result.selected_option == "bigco"

    def test_multi_option_never_produces_reject(self) -> None:
        # spec §8: only ACCEPT ("pick selected_option") or UNCERTAIN, never REJECT -
        # there is no "runner-up is worse than nothing" concept without a status quo.
        close_options = [
            ("a", factor_vector({"skill_growth": "moderate"})),
            ("b", factor_vector({"skill_growth": "moderate"})),
            ("c", factor_vector({"skill_growth": "moderate"})),
        ]
        result = decide_multi_option(TAXONOMY, T_REF_WEIGHTS, close_options, T_REF_DISPOSITIONS)
        assert result.label is not DecisionOutcome.REJECT

    def test_unselected_option_leaves_selected_option_none(self) -> None:
        tied = [
            ("a", factor_vector({"skill_growth": "moderate"})),
            ("b", factor_vector({"skill_growth": "moderate"})),
            ("c", factor_vector({"skill_growth": "moderate"})),
        ]
        result = decide_multi_option(TAXONOMY, T_REF_WEIGHTS, tied, T_REF_DISPOSITIONS)
        if result.label is not DecisionOutcome.ACCEPT:
            assert result.selected_option is None
