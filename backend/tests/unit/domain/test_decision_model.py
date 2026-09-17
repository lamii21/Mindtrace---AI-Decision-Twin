"""Construction-time invariants of `mindtrace.domain.decision`'s value types.

M3 s: "do not silently clamp invalid scientific inputs" and "do not
automatically fix obviously malformed weights unless the spec says to
normalize them" - these tests confirm the malformed shapes actually raise,
rather than being coerced.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mindtrace.domain.decision import DispositionInputs, FactorReading, FactorVector, WeightVector
from mindtrace.domain.enums import ScaleLevel
from mindtrace.domain.ids import FactorId


class TestFactorReading:
    def test_known_true_requires_a_level(self) -> None:
        with pytest.raises(ValidationError):
            FactorReading(known=True, level=None)

    def test_known_false_must_not_carry_a_level(self) -> None:
        with pytest.raises(ValidationError):
            FactorReading(known=False, level=ScaleLevel.HIGH)

    def test_known_true_with_level_is_valid(self) -> None:
        reading = FactorReading(known=True, level=ScaleLevel.HIGH)
        assert reading.level is ScaleLevel.HIGH

    def test_known_false_without_level_is_valid(self) -> None:
        reading = FactorReading(known=False)
        assert reading.level is None

    def test_is_frozen(self) -> None:
        reading = FactorReading(known=False)
        with pytest.raises(ValidationError):
            reading.known = True


class TestFactorVector:
    def test_from_items_rejects_duplicate_factor_ids(self) -> None:
        fid = FactorId("skill_growth")
        with pytest.raises(ValueError, match="duplicate factor id"):
            FactorVector.from_items(
                [
                    (fid, FactorReading(known=True, level=ScaleLevel.HIGH)),
                    (fid, FactorReading(known=False)),
                ]
            )

    def test_known_ids_excludes_unknown_and_is_sorted(self) -> None:
        vector = FactorVector.from_items(
            [
                (FactorId("skill_growth"), FactorReading(known=True, level=ScaleLevel.HIGH)),
                (FactorId("autonomy"), FactorReading(known=False)),
                (FactorId("downside_risk"), FactorReading(known=True, level=ScaleLevel.LOW)),
            ]
        )
        assert vector.known_ids() == (FactorId("downside_risk"), FactorId("skill_growth"))

    def test_empty_factor_vector_is_valid_with_no_known_ids(self) -> None:
        vector = FactorVector.from_items([])
        assert vector.known_ids() == ()


class TestWeightVector:
    def test_empty_weights_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must not be empty"):
            WeightVector(weights={})

    def test_negative_weight_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="negative"):
            WeightVector(weights={FactorId("skill_growth"): -0.1, FactorId("autonomy"): 1.1})

    def test_weights_not_summing_to_one_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match=r"must sum to 1\.0"):
            WeightVector(weights={FactorId("skill_growth"): 0.5, FactorId("autonomy"): 0.4})

    def test_weights_summing_to_one_within_tolerance_are_accepted(self) -> None:
        vector = WeightVector(
            weights={FactorId("skill_growth"): 0.5, FactorId("autonomy"): 0.5000005}
        )
        assert vector.weights[FactorId("autonomy")] == 0.5000005

    def test_a_single_factor_with_weight_one_is_valid(self) -> None:
        vector = WeightVector(weights={FactorId("skill_growth"): 1.0})
        assert vector.weights == {FactorId("skill_growth"): 1.0}

    def test_zero_weight_on_one_factor_is_allowed_if_the_rest_still_sum_to_one(self) -> None:
        vector = WeightVector(weights={FactorId("skill_growth"): 1.0, FactorId("autonomy"): 0.0})
        assert vector.weights[FactorId("autonomy")] == 0.0


class TestDispositionInputs:
    def test_neutral_is_all_one_half(self) -> None:
        neutral = DispositionInputs.neutral()
        assert neutral.risk_tolerance == 0.5
        assert neutral.time_discount == 0.5
        assert neutral.ambiguity_aversion == 0.5
        assert neutral.effort_tolerance == 0.5

    @pytest.mark.parametrize(
        "field", ["risk_tolerance", "time_discount", "ambiguity_aversion", "effort_tolerance"]
    )
    def test_out_of_range_dispositions_are_rejected(self, field: str) -> None:
        base = {
            "risk_tolerance": 0.5,
            "time_discount": 0.5,
            "ambiguity_aversion": 0.5,
            "effort_tolerance": 0.5,
        }
        base[field] = 1.5
        with pytest.raises(ValidationError):
            DispositionInputs(**base)
