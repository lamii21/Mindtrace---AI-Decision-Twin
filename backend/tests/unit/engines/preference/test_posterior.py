"""Posterior read-side: `softmax_over_known`, confidence, credible intervals, and the
effective-sample-size / `DispositionInputs` bridges."""

from __future__ import annotations

import math

import pytest
from tests.support.preference_fixtures import TRAIT_MODEL

from mindtrace.domain.ids import DispositionId, FactorId
from mindtrace.domain.traits import DispositionPosterior, WeightPosterior
from mindtrace.engines.preference.posterior import (
    disposition_confidence,
    disposition_credible_interval,
    disposition_report,
    disposition_value,
    effective_sample_sizes,
    softmax_over_known,
    to_disposition_inputs,
    weight_confidence,
    weight_credible_interval,
    weight_report,
)


class TestSoftmaxOverKnown:
    def test_equal_mu_gives_equal_shares(self) -> None:
        weights = {
            FactorId("a"): WeightPosterior(factor=FactorId("a"), mu=0.0, sigma=1.0),
            FactorId("b"): WeightPosterior(factor=FactorId("b"), mu=0.0, sigma=1.0),
        }
        result = softmax_over_known(weights, [FactorId("a"), FactorId("b")])
        assert result[FactorId("a")] == pytest.approx(0.5)
        assert result[FactorId("b")] == pytest.approx(0.5)

    def test_sums_to_one(self) -> None:
        weights = {
            FactorId("a"): WeightPosterior(factor=FactorId("a"), mu=0.7, sigma=1.0),
            FactorId("b"): WeightPosterior(factor=FactorId("b"), mu=-0.3, sigma=1.0),
            FactorId("c"): WeightPosterior(factor=FactorId("c"), mu=1.2, sigma=1.0),
        }
        result = softmax_over_known(weights, list(weights))
        assert sum(result.values()) == pytest.approx(1.0)

    def test_empty_known_ids_gives_empty_result(self) -> None:
        weights = {FactorId("a"): WeightPosterior(factor=FactorId("a"), mu=0.0, sigma=1.0)}
        assert softmax_over_known(weights, []) == {}

    def test_higher_mu_gives_a_higher_share(self) -> None:
        weights = {
            FactorId("a"): WeightPosterior(factor=FactorId("a"), mu=2.0, sigma=1.0),
            FactorId("b"): WeightPosterior(factor=FactorId("b"), mu=-2.0, sigma=1.0),
        }
        result = softmax_over_known(weights, [FactorId("a"), FactorId("b")])
        assert result[FactorId("a")] > result[FactorId("b")]

    def test_restricts_to_only_the_known_subset(self) -> None:
        weights = {
            FactorId("a"): WeightPosterior(factor=FactorId("a"), mu=0.0, sigma=1.0),
            FactorId("b"): WeightPosterior(factor=FactorId("b"), mu=100.0, sigma=1.0),
        }
        result = softmax_over_known(weights, [FactorId("a")])
        assert result == {FactorId("a"): pytest.approx(1.0)}


class TestWeightConfidence:
    def test_no_narrowing_gives_zero_confidence(self) -> None:
        posterior = WeightPosterior(factor=FactorId("a"), mu=0.0, sigma=1.5)
        assert weight_confidence(posterior, prior_sigma=1.5) == pytest.approx(0.0)

    def test_full_narrowing_gives_confidence_near_one(self) -> None:
        posterior = WeightPosterior(factor=FactorId("a"), mu=0.0, sigma=0.001)
        assert weight_confidence(posterior, prior_sigma=1.5) > 0.99

    def test_widening_past_the_prior_is_clipped_to_zero(self) -> None:
        posterior = WeightPosterior(factor=FactorId("a"), mu=0.0, sigma=3.0)
        assert weight_confidence(posterior, prior_sigma=1.5) == 0.0


class TestDispositionValueAndConfidence:
    def test_symmetric_beta_gives_value_one_half(self) -> None:
        posterior = DispositionPosterior(id=DispositionId("risk_tolerance"), alpha=2.0, beta=2.0)
        assert disposition_value(posterior) == pytest.approx(0.5)

    def test_skewed_beta_gives_a_skewed_value(self) -> None:
        posterior = DispositionPosterior(id=DispositionId("risk_tolerance"), alpha=8.0, beta=2.0)
        assert disposition_value(posterior) == pytest.approx(0.8)

    def test_prior_shaped_beta_gives_zero_confidence(self) -> None:
        posterior = DispositionPosterior(id=DispositionId("risk_tolerance"), alpha=2.0, beta=2.0)
        assert disposition_confidence(posterior) == pytest.approx(0.0, abs=1e-9)

    def test_narrower_beta_gives_higher_confidence(self) -> None:
        wide = DispositionPosterior(id=DispositionId("risk_tolerance"), alpha=2.0, beta=2.0)
        narrow = DispositionPosterior(id=DispositionId("risk_tolerance"), alpha=50.0, beta=50.0)
        assert disposition_confidence(narrow) > disposition_confidence(wide)


class TestCredibleIntervals:
    def test_weight_credible_interval_contains_the_point_value(self) -> None:
        weights = {
            FactorId("a"): WeightPosterior(factor=FactorId("a"), mu=0.2, sigma=1.0),
            FactorId("b"): WeightPosterior(factor=FactorId("b"), mu=-0.1, sigma=1.0),
        }
        known = [FactorId("a"), FactorId("b")]
        value = softmax_over_known(weights, known)[FactorId("a")]
        ci = weight_credible_interval(weights, known, FactorId("a"))
        assert ci.low <= value <= ci.high

    def test_narrower_weight_posterior_gives_a_narrower_interval(self) -> None:
        wide = {
            FactorId("a"): WeightPosterior(factor=FactorId("a"), mu=0.0, sigma=1.5),
            FactorId("b"): WeightPosterior(factor=FactorId("b"), mu=0.0, sigma=1.5),
        }
        narrow = {
            FactorId("a"): WeightPosterior(factor=FactorId("a"), mu=0.0, sigma=0.2),
            FactorId("b"): WeightPosterior(factor=FactorId("b"), mu=0.0, sigma=1.5),
        }
        known = [FactorId("a"), FactorId("b")]
        wide_ci = weight_credible_interval(wide, known, FactorId("a"))
        narrow_ci = weight_credible_interval(narrow, known, FactorId("a"))
        assert (narrow_ci.high - narrow_ci.low) < (wide_ci.high - wide_ci.low)

    def test_disposition_credible_interval_contains_the_point_value(self) -> None:
        posterior = DispositionPosterior(id=DispositionId("risk_tolerance"), alpha=5.0, beta=3.0)
        ci = disposition_credible_interval(posterior)
        assert ci.low <= disposition_value(posterior) <= ci.high

    def test_disposition_credible_interval_stays_within_unit_range(self) -> None:
        posterior = DispositionPosterior(id=DispositionId("risk_tolerance"), alpha=2.0, beta=2.0)
        ci = disposition_credible_interval(posterior)
        assert ci.low >= 0.0
        assert ci.high <= 1.0


class TestEffectiveSampleSizes:
    def test_prior_equals_posterior_gives_zero_n_eff(self) -> None:
        weights = {
            fid: WeightPosterior(factor=fid, mu=w.prior.mu, sigma=w.prior.sigma)
            for fid, w in ((w.factor, w) for w in TRAIT_MODEL.weights)
        }
        n_eff = effective_sample_sizes(weights, TRAIT_MODEL)
        assert all(value == pytest.approx(0.0) for value in n_eff.values())

    def test_narrower_posterior_gives_positive_n_eff(self) -> None:
        first_weight = TRAIT_MODEL.weights[0]
        weights = {
            fid: WeightPosterior(factor=fid, mu=w.prior.mu, sigma=w.prior.sigma)
            for fid, w in ((w.factor, w) for w in TRAIT_MODEL.weights)
        }
        narrowed_sigma = first_weight.prior.sigma / 2.0
        weights[first_weight.factor] = WeightPosterior(
            factor=first_weight.factor, mu=first_weight.prior.mu, sigma=narrowed_sigma
        )
        n_eff = effective_sample_sizes(weights, TRAIT_MODEL)
        assert n_eff[first_weight.factor] == pytest.approx(
            (first_weight.prior.sigma**2) / (narrowed_sigma**2) - 1.0
        )

    def test_matches_the_hand_computed_formula_at_n_bar_four(self) -> None:
        first_weight = TRAIT_MODEL.weights[0]
        prior_sigma = first_weight.prior.sigma
        # solve prior_sigma^2/sigma^2 - 1 = 4 -> sigma = prior_sigma/sqrt(5)
        sigma = prior_sigma / math.sqrt(5.0)
        weights = {
            fid: WeightPosterior(factor=fid, mu=w.prior.mu, sigma=w.prior.sigma)
            for fid, w in ((w.factor, w) for w in TRAIT_MODEL.weights)
        }
        weights[first_weight.factor] = WeightPosterior(
            factor=first_weight.factor, mu=first_weight.prior.mu, sigma=sigma
        )
        n_eff = effective_sample_sizes(weights, TRAIT_MODEL)
        assert n_eff[first_weight.factor] == pytest.approx(4.0, abs=1e-6)


class TestToDispositionInputs:
    def test_reads_beta_means_for_every_disposition(self) -> None:
        dispositions = {
            DispositionId("risk_tolerance"): DispositionPosterior(
                id=DispositionId("risk_tolerance"), alpha=6.0, beta=2.0
            ),
            DispositionId("time_discount"): DispositionPosterior(
                id=DispositionId("time_discount"), alpha=2.0, beta=2.0
            ),
            DispositionId("ambiguity_aversion"): DispositionPosterior(
                id=DispositionId("ambiguity_aversion"), alpha=3.0, beta=1.0
            ),
            DispositionId("effort_tolerance"): DispositionPosterior(
                id=DispositionId("effort_tolerance"), alpha=1.0, beta=3.0
            ),
        }
        inputs = to_disposition_inputs(dispositions)
        assert inputs.risk_tolerance == pytest.approx(0.75)
        assert inputs.time_discount == pytest.approx(0.5)
        assert inputs.ambiguity_aversion == pytest.approx(0.75)
        assert inputs.effort_tolerance == pytest.approx(0.25)


class TestReports:
    def test_weight_report_source_is_declared_below_the_evidence_threshold(self) -> None:
        weights = {
            fid: WeightPosterior(factor=fid, mu=w.prior.mu, sigma=w.prior.sigma)
            for fid, w in ((w.factor, w) for w in TRAIT_MODEL.weights)
        }
        factor_id = TRAIT_MODEL.weights[0].factor
        report = weight_report(weights, list(weights), factor_id, TRAIT_MODEL, evidence_count=0)
        assert report.source == "declared"

    def test_weight_report_source_is_inferred_at_the_evidence_threshold(self) -> None:
        weights = {
            fid: WeightPosterior(factor=fid, mu=w.prior.mu, sigma=w.prior.sigma)
            for fid, w in ((w.factor, w) for w in TRAIT_MODEL.weights)
        }
        factor_id = TRAIT_MODEL.weights[0].factor
        threshold = TRAIT_MODEL.report.min_evidence_for_inferred
        report = weight_report(
            weights, list(weights), factor_id, TRAIT_MODEL, evidence_count=threshold
        )
        assert report.source == "inferred"

    def test_disposition_report_source_is_declared_below_the_evidence_threshold(self) -> None:
        posterior = DispositionPosterior(id=DispositionId("risk_tolerance"), alpha=2.0, beta=2.0)
        report = disposition_report(posterior, TRAIT_MODEL, evidence_count=0)
        assert report.source == "declared"

    def test_disposition_report_source_is_inferred_at_the_evidence_threshold(self) -> None:
        posterior = DispositionPosterior(id=DispositionId("risk_tolerance"), alpha=2.0, beta=2.0)
        threshold = TRAIT_MODEL.report.min_evidence_for_inferred
        report = disposition_report(posterior, TRAIT_MODEL, evidence_count=threshold)
        assert report.source == "inferred"
