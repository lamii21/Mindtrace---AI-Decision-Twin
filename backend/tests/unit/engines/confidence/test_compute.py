"""`compute_confidence`: orchestration, missing-data semantics, and the S/C separation guarantee.

The M4 prompt's absolute invariant: `C != abs(S)`, and confidence must never
be derivable as a pure function of `S` alone. These tests demonstrate that
concretely, not just by construction.
"""

from __future__ import annotations

import pytest
from tests.support.confidence_fixtures import (
    DECISION_EXAMPLE_1,
    DECISION_EXAMPLE_2,
    DECISION_EXAMPLE_3,
    DECISION_EXAMPLE_4,
    DECISION_EXAMPLE_5,
    DISAGREEING_ENSEMBLE,
    GENEROUS_N_EFF,
    POORLY_CALIBRATED_LEDGER,
    UNANIMOUS_ENSEMBLE,
    WELL_CALIBRATED_LEDGER,
    self_consistency_signal,
)

from mindtrace.domain.confidence import ConfidenceInputs, ConfidenceResult, ExtractionSignal
from mindtrace.domain.decision import DecisionResult
from mindtrace.domain.ids import FactorId
from mindtrace.engines.confidence._numeric import stable_sigmoid
from mindtrace.engines.confidence.compute import (
    compute_confidence,
    confidence_uncertain_reason,
    is_low_confidence,
)
from mindtrace.engines.confidence.config import (
    DEFAULT_CONFIDENCE_CONFIG,
    ConfidenceConfig,
    RecalibrationParams,
)
from mindtrace.engines.confidence.errors import ConfidenceValidationError

_GOLDEN_DECISIONS = [
    DECISION_EXAMPLE_1,
    DECISION_EXAMPLE_2,
    DECISION_EXAMPLE_3,
    DECISION_EXAMPLE_4,
    DECISION_EXAMPLE_5,
]


class TestColdStartDefaults:
    """No posteriors, no ensemble, no ledger, no extraction pipeline exist yet."""

    def test_extraction_path_is_unavailable_by_default(self) -> None:
        result = compute_confidence(DECISION_EXAMPLE_1)
        assert result.inputs.extraction_path == "unavailable"
        assert result.inputs.extraction_entropy is None

    def test_calibrated_is_false_by_default(self) -> None:
        result = compute_confidence(DECISION_EXAMPLE_1)
        assert result.inputs.calibrated == "false"
        assert result.inputs.historical_calibration is None
        assert result.inputs.calibration_n == 0

    def test_ensemble_disagreement_is_none_by_default(self) -> None:
        result = compute_confidence(DECISION_EXAMPLE_1)
        assert result.inputs.ensemble_disagreement is None
        assert result.inputs.ensemble_term_capped is False

    def test_evidence_sufficiency_is_zero_by_default(self) -> None:
        """The honest state: no preference engine has ever updated a weight posterior."""
        result = compute_confidence(DECISION_EXAMPLE_1)
        assert result.inputs.evidence_sufficiency == 0.0
        assert result.inputs.n_bar == 0.0

    def test_only_a_and_e_survive_renormalization(self) -> None:
        result = compute_confidence(DECISION_EXAMPLE_1)
        assert set(result.weights_used) == {"A", "E"}

    def test_calibrated_output_is_false_with_no_recalibration_config(self) -> None:
        result = compute_confidence(DECISION_EXAMPLE_1)
        assert result.calibrated_output is False
        assert result.value == result.raw

    def test_credible_interval_is_not_computed(self) -> None:
        result = compute_confidence(DECISION_EXAMPLE_1)
        assert result.credible_interval is None


class TestSeparationFromScore:
    """Section 3's absolute invariant: `C != abs(S)`, and `C` is not a function of `S` alone."""

    @pytest.mark.parametrize("decision", _GOLDEN_DECISIONS, ids=lambda d: f"score={d.score:.3f}")
    def test_c_never_equals_abs_s(self, decision: DecisionResult) -> None:
        result = compute_confidence(decision)
        assert result.value != pytest.approx(abs(decision.score))

    def test_high_score_can_coexist_with_low_confidence(self) -> None:
        # Example 1: S = 0.69 (strong ACCEPT lean) but no evidence/ensemble/calibration/
        # extraction data at all -> C is low, dominated by margin_adequacy alone.
        result = compute_confidence(DECISION_EXAMPLE_1)
        assert DECISION_EXAMPLE_1.score > 0.6
        assert result.value < 0.4

    def test_confidence_is_unchanged_when_only_the_scores_sign_flips(self) -> None:
        """`compute_confidence` never reads `decision.score` - only `margin`/`coverage`/
        `contributions` - so flipping S's sign while holding everything else fixed
        cannot change `C` at all. This is the architectural guarantee behind `C != abs(S)`,
        not just a coincidence of the golden examples."""
        flipped = DECISION_EXAMPLE_1.model_copy(
            update={"score": -DECISION_EXAMPLE_1.score, "raw_score": -DECISION_EXAMPLE_1.raw_score}
        )
        original_result = compute_confidence(DECISION_EXAMPLE_1, n_eff=GENEROUS_N_EFF)
        flipped_result = compute_confidence(flipped, n_eff=GENEROUS_N_EFF)
        assert original_result.value == flipped_result.value
        assert original_result.raw == flipped_result.raw

    def test_same_score_different_confidence_via_ensemble_disagreement(self) -> None:
        """Two computations over the *same* `DecisionResult` (same `S`) diverge in `C`
        purely because one supplies ensemble disagreement data and the other doesn't -
        proof that `C` carries information `S` does not."""
        without_ensemble = compute_confidence(DECISION_EXAMPLE_1, n_eff=GENEROUS_N_EFF)
        with_disagreement = compute_confidence(
            DECISION_EXAMPLE_1, n_eff=GENEROUS_N_EFF, ensemble=DISAGREEING_ENSEMBLE
        )
        assert without_ensemble.value != with_disagreement.value

    def test_same_score_different_confidence_via_calibration(self) -> None:
        well_calibrated = compute_confidence(DECISION_EXAMPLE_1, calibration=WELL_CALIBRATED_LEDGER)
        poorly_calibrated = compute_confidence(
            DECISION_EXAMPLE_1, calibration=POORLY_CALIBRATED_LEDGER
        )
        assert well_calibrated.value > poorly_calibrated.value


class TestFullSignalComposition:
    """When every signal is actually supplied, all five weights A-E survive unrenormalized."""

    def test_all_five_terms_present_when_every_signal_is_supplied(self) -> None:
        result = compute_confidence(
            DECISION_EXAMPLE_1,
            n_eff=GENEROUS_N_EFF,
            ensemble=UNANIMOUS_ENSEMBLE,
            calibration=WELL_CALIBRATED_LEDGER,
            extraction=self_consistency_signal(1.0, DECISION_EXAMPLE_1),
        )
        assert set(result.weights_used) == {"A", "B", "C", "D", "E"}
        assert result.weights_used["A"] == pytest.approx(DEFAULT_CONFIDENCE_CONFIG.a_evidence)

    def test_full_evidence_and_agreement_gives_a_meaningfully_higher_confidence(self) -> None:
        cold_start = compute_confidence(DECISION_EXAMPLE_1)
        fully_evidenced = compute_confidence(
            DECISION_EXAMPLE_1,
            n_eff=GENEROUS_N_EFF,
            ensemble=UNANIMOUS_ENSEMBLE,
            calibration=WELL_CALIBRATED_LEDGER,
            extraction=self_consistency_signal(1.0, DECISION_EXAMPLE_1),
        )
        assert fully_evidenced.value > cold_start.value

    def test_extraction_mismatch_raises(self) -> None:
        bad_signal = ExtractionSignal.self_consistency({FactorId("skill_growth"): 1.0})
        with pytest.raises(ConfidenceValidationError):
            compute_confidence(DECISION_EXAMPLE_1, extraction=bad_signal)


class TestThresholdBoundary:
    """Section 17: exact boundary semantics for the `C < C_MIN` gate, `C_MIN` itself excluded."""

    def _result_with_value(self, value: float) -> tuple[ConfidenceResult, ConfidenceConfig]:
        config = ConfidenceConfig(c_min=0.35)
        result = ConfidenceResult(
            confidence_engine_version="1",
            confidence_config_version="1",
            value=value,
            raw=value,
            calibrated_output=False,
            credible_interval=None,
            inputs=ConfidenceInputs(
                evidence_sufficiency=0.0,
                n_bar=0.0,
                coverage=1.0,
                ensemble_disagreement=None,
                ensemble_term_capped=False,
                historical_calibration=None,
                calibrated="false",
                calibration_n=0,
                extraction_entropy=None,
                extraction_path="unavailable",
                margin_adequacy=value,
                margin=0.1,
            ),
            weights_used={"E": 1.0},
        )
        return result, config

    def test_just_below_threshold_is_low_confidence(self) -> None:
        result, config = self._result_with_value(0.349999)
        assert is_low_confidence(result, config) is True
        assert confidence_uncertain_reason(result, config) is not None

    def test_exactly_at_threshold_is_not_low_confidence(self) -> None:
        # spec: `C < C_MIN` fires the gate - equality does not.
        result, config = self._result_with_value(0.35)
        assert is_low_confidence(result, config) is False
        assert confidence_uncertain_reason(result, config) is None

    def test_just_above_threshold_is_not_low_confidence(self) -> None:
        result, config = self._result_with_value(0.350001)
        assert is_low_confidence(result, config) is False


class TestDeterminism:
    def test_same_inputs_give_byte_identical_result(self) -> None:
        first = compute_confidence(
            DECISION_EXAMPLE_1, n_eff=GENEROUS_N_EFF, ensemble=UNANIMOUS_ENSEMBLE
        )
        second = compute_confidence(
            DECISION_EXAMPLE_1, n_eff=GENEROUS_N_EFF, ensemble=UNANIMOUS_ENSEMBLE
        )
        assert first.model_dump_json() == second.model_dump_json()


class TestRecalibration:
    """spec §06 §8: once a `RecalibrationParams` pair is configured, `C` uses it - but only
    a config that explicitly carries one activates this path; the default never does."""

    def test_no_recalibration_configured_reports_raw_c_directly(self) -> None:
        result = compute_confidence(DECISION_EXAMPLE_1, config=DEFAULT_CONFIDENCE_CONFIG)
        assert result.calibrated_output is False
        assert result.value == result.raw

    def test_configured_recalibration_applies_the_logistic_map(self) -> None:
        config = ConfidenceConfig(recalibration=RecalibrationParams(alpha=0.1, beta=2.0))
        result = compute_confidence(DECISION_EXAMPLE_1, config=config)
        assert result.calibrated_output is True
        expected = stable_sigmoid(0.1 + 2.0 * result.raw)
        assert result.value == pytest.approx(expected, abs=1e-12)
        assert result.value != result.raw
