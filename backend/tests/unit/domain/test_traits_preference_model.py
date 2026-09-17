"""Construction-time invariants of the M4 additions to `mindtrace.domain.traits`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mindtrace.domain.ids import DispositionId, FactorId
from mindtrace.domain.traits import (
    CredibleInterval,
    DispositionObservation,
    DispositionPosterior,
    PairwiseObservation,
    PreferencePosterior,
    TraitReport,
    WeightPosterior,
)


class TestWeightPosterior:
    def test_sigma_must_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="sigma must be > 0"):
            WeightPosterior(factor=FactorId("skill_growth"), mu=0.0, sigma=0.0)

    def test_valid_posterior_is_accepted(self) -> None:
        posterior = WeightPosterior(factor=FactorId("skill_growth"), mu=0.2, sigma=1.1)
        assert posterior.mu == 0.2

    def test_is_frozen(self) -> None:
        posterior = WeightPosterior(factor=FactorId("skill_growth"), mu=0.2, sigma=1.1)
        with pytest.raises(ValidationError):
            posterior.mu = 0.9


class TestDispositionPosterior:
    @pytest.mark.parametrize(("alpha", "beta"), [(0.0, 2.0), (2.0, 0.0), (-1.0, 2.0)])
    def test_parameters_must_be_positive(self, alpha: float, beta: float) -> None:
        with pytest.raises(ValidationError, match="Beta parameters must be > 0"):
            DispositionPosterior(id=DispositionId("risk_tolerance"), alpha=alpha, beta=beta)

    def test_valid_posterior_is_accepted(self) -> None:
        posterior = DispositionPosterior(id=DispositionId("risk_tolerance"), alpha=2.0, beta=2.0)
        assert posterior.alpha == 2.0


class TestPairwiseObservation:
    def test_empty_design_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="at least one factor"):
            PairwiseObservation(design={}, outcome=1.0, weight=1.0)

    def test_outcome_out_of_range_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PairwiseObservation(design={FactorId("skill_growth"): 1.0}, outcome=1.5, weight=1.0)

    def test_weight_out_of_range_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PairwiseObservation(design={FactorId("skill_growth"): 1.0}, outcome=1.0, weight=0.0)

    def test_valid_observation_is_accepted(self) -> None:
        obs = PairwiseObservation(design={FactorId("skill_growth"): 0.5}, outcome=0.5, weight=0.5)
        assert obs.outcome == 0.5


class TestDispositionObservation:
    def test_outcome_out_of_range_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DispositionObservation(target=DispositionId("risk_tolerance"), outcome=-0.1)

    def test_valid_observation_is_accepted(self) -> None:
        obs = DispositionObservation(target=DispositionId("risk_tolerance"), outcome=1.0)
        assert obs.outcome == 1.0


class TestPreferencePosterior:
    def _build(self, **overrides: object) -> PreferencePosterior:
        base = {
            "engine_version": "1",
            "trait_schema_version": 1,
            "weights": {
                FactorId("skill_growth"): WeightPosterior(
                    factor=FactorId("skill_growth"), mu=0.0, sigma=1.4
                )
            },
            "weight_evidence_count": {FactorId("skill_growth"): 0},
            "dispositions": {
                DispositionId("risk_tolerance"): DispositionPosterior(
                    id=DispositionId("risk_tolerance"), alpha=2.0, beta=2.0
                )
            },
            "disposition_evidence_count": {DispositionId("risk_tolerance"): 0},
        }
        base.update(overrides)
        return PreferencePosterior(**base)  # type: ignore[arg-type]

    def test_valid_posterior_is_accepted(self) -> None:
        posterior = self._build()
        assert posterior.trait_schema_version == 1

    def test_weight_evidence_count_keys_must_match_weights(self) -> None:
        with pytest.raises(ValidationError, match="weight_evidence_count"):
            self._build(weight_evidence_count={})

    def test_disposition_evidence_count_keys_must_match_dispositions(self) -> None:
        with pytest.raises(ValidationError, match="disposition_evidence_count"):
            self._build(disposition_evidence_count={})

    def test_negative_weight_evidence_count_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="negative"):
            self._build(weight_evidence_count={FactorId("skill_growth"): -1})

    def test_negative_disposition_evidence_count_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="negative"):
            self._build(disposition_evidence_count={DispositionId("risk_tolerance"): -1})


class TestCredibleInterval:
    def test_low_above_high_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must not exceed"):
            CredibleInterval(low=0.9, high=0.1)

    def test_low_equal_high_is_accepted(self) -> None:
        ci = CredibleInterval(low=0.5, high=0.5)
        assert ci.low == ci.high


class TestTraitReport:
    def _build(self, **overrides: object) -> TraitReport:
        base = {
            "id": "skill_growth",
            "value": 0.2,
            "confidence": 0.5,
            "credible_interval": CredibleInterval(low=0.1, high=0.3),
            "evidence_count": 2,
            "source": "declared",
        }
        base.update(overrides)
        return TraitReport(**base)  # type: ignore[arg-type]

    def test_valid_report_is_accepted(self) -> None:
        report = self._build()
        assert report.source == "declared"

    def test_invalid_source_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match=r"declared.*inferred"):
            self._build(source="observed")

    def test_confidence_out_of_range_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._build(confidence=1.5)

    def test_negative_evidence_count_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._build(evidence_count=-1)
