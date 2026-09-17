"""Construction-time invariants of `mindtrace.domain.confidence`'s value types.

Section 9 of the M4 prompt: "Reject C < 0, C > 1, NaN, infinity... use explicit
numerical validation" - these tests confirm the domain boundary actually does.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from mindtrace.domain.confidence import (
    CalibrationRecord,
    ConfidenceInputs,
    ConfidenceResult,
    EnsembleObservation,
    ExtractionSignal,
)
from mindtrace.domain.enums import DecisionOutcome
from mindtrace.domain.ids import FactorId

_INPUTS_KWARGS = {
    "evidence_sufficiency": 0.5,
    "n_bar": 4.0,
    "coverage": 0.7,
    "ensemble_disagreement": None,
    "ensemble_term_capped": False,
    "historical_calibration": None,
    "calibrated": "false",
    "calibration_n": 0,
    "extraction_entropy": None,
    "extraction_path": "unavailable",
    "margin_adequacy": 0.6,
    "margin": 0.1,
}


class TestEnsembleObservation:
    def test_requires_at_least_two_scores(self) -> None:
        with pytest.raises(ValidationError, match=">= 2 scores"):
            EnsembleObservation(scores=(0.5,), labels=(DecisionOutcome.ACCEPT,))

    def test_labels_must_match_scores_length(self) -> None:
        with pytest.raises(ValidationError, match="same length"):
            EnsembleObservation(
                scores=(0.5, 0.6),
                labels=(DecisionOutcome.ACCEPT,),
            )

    def test_score_out_of_range_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match=r"out of \[-1, 1\]"):
            EnsembleObservation(
                scores=(0.5, 1.5),
                labels=(DecisionOutcome.ACCEPT, DecisionOutcome.ACCEPT),
            )

    def test_valid_observation_is_accepted(self) -> None:
        obs = EnsembleObservation(
            scores=(0.5, -0.3, 0.1),
            labels=(DecisionOutcome.ACCEPT, DecisionOutcome.REJECT, DecisionOutcome.UNCERTAIN),
        )
        assert obs.scores == (0.5, -0.3, 0.1)


class TestCalibrationRecord:
    def test_predicted_confidence_out_of_range_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CalibrationRecord(predicted_confidence=1.1, correct=True)

    def test_valid_record_is_accepted(self) -> None:
        record = CalibrationRecord(predicted_confidence=0.7, correct=False)
        assert record.correct is False


class TestExtractionSignal:
    def test_single_path_is_valid(self) -> None:
        signal = ExtractionSignal.single()
        assert signal.path == "single"
        assert signal.agreement is None

    def test_single_path_must_not_carry_agreement(self) -> None:
        with pytest.raises(ValidationError, match="single"):
            ExtractionSignal(path="single", agreement={FactorId("skill_growth"): 1.0})

    def test_self_consistency_requires_nonempty_agreement(self) -> None:
        with pytest.raises(ValidationError, match="self_consistency"):
            ExtractionSignal(path="self_consistency", agreement={})

    def test_self_consistency_agreement_out_of_range_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match=r"out of \[0, 1\]"):
            ExtractionSignal.self_consistency({FactorId("skill_growth"): 1.5})

    def test_unknown_path_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="'single' or 'self_consistency'"):
            ExtractionSignal(path="bogus")

    def test_self_consistency_with_valid_agreement_is_accepted(self) -> None:
        signal = ExtractionSignal.self_consistency({FactorId("skill_growth"): 0.5})
        assert signal.agreement == {FactorId("skill_growth"): 0.5}


class TestConfidenceResult:
    def _inputs(self) -> ConfidenceInputs:
        return ConfidenceInputs(**_INPUTS_KWARGS)  # type: ignore[arg-type]

    def _build(self, *, value: float, raw: float) -> ConfidenceResult:
        return ConfidenceResult(
            confidence_engine_version="1",
            confidence_config_version="1",
            value=value,
            raw=raw,
            calibrated_output=False,
            credible_interval=None,
            inputs=self._inputs(),
            weights_used={"A": 0.7, "E": 0.3},
        )

    def test_value_above_one_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._build(value=1.1, raw=0.5)

    def test_value_below_zero_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._build(value=-0.1, raw=0.5)

    def test_nan_value_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._build(value=math.nan, raw=0.5)

    def test_infinite_value_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._build(value=math.inf, raw=0.5)

    def test_valid_result_is_accepted(self) -> None:
        result = self._build(value=0.42, raw=0.42)
        assert result.value == 0.42
        assert result.credible_interval is None

    def test_is_frozen(self) -> None:
        result = self._build(value=0.5, raw=0.5)
        with pytest.raises(ValidationError):
            result.value = 0.9
