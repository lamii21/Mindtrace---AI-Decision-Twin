"""`project_effective_weights`: the full M6-A test matrix (A-L)."""

from __future__ import annotations

import math

import pytest
from tests.support.mcda_fixtures import TAXONOMY as MCDA_TAXONOMY
from tests.support.preference_fixtures import TAXONOMY, TRAIT_MODEL

from mindtrace.domain.decision import FactorReading, FactorVector
from mindtrace.domain.enums import ScaleLevel
from mindtrace.domain.ids import DispositionId, FactorId
from mindtrace.domain.traits import DispositionPosterior, PairwiseObservation, WeightPosterior
from mindtrace.engines.mcda.decide import decide
from mindtrace.engines.preference.config import DEFAULT_PREFERENCE_CONFIG, PROJECTION_VERSION
from mindtrace.engines.preference.errors import PreferenceValidationError
from mindtrace.engines.preference.posterior import softmax_over_known
from mindtrace.engines.preference.prior import initial_posterior
from mindtrace.engines.preference.projection import project_effective_weights
from mindtrace.engines.preference.update import apply_pairwise_observations

_FID_A = FactorId("skill_growth")
_FID_B = FactorId("financial_return")
_AUTONOMY = FactorId("autonomy")
_STABILITY = FactorId("stability")


class TestColdStart:
    """A. zero observations -> prior -> deterministic effective weights."""

    def test_cold_start_weights_match_hand_computed_softmax_of_the_prior(self) -> None:
        posterior = initial_posterior(TRAIT_MODEL)
        snapshot = project_effective_weights(posterior, TRAIT_MODEL)

        core_ids = TRAIT_MODEL.core_weight_factor_ids
        mus = [TRAIT_MODEL.weight_for(fid).prior.mu for fid in core_ids]
        shift = max(mus)
        exponentials = [math.exp(mu - shift) for mu in mus]
        total = sum(exponentials)
        expected = dict(zip(core_ids, (v / total for v in exponentials), strict=True))

        for factor_id, expected_weight in expected.items():
            assert snapshot.weights.weights[factor_id] == pytest.approx(expected_weight, abs=1e-12)

    def test_cold_start_dispositions_match_prior_beta_means(self) -> None:
        posterior = initial_posterior(TRAIT_MODEL)
        snapshot = project_effective_weights(posterior, TRAIT_MODEL)
        risk_prior = TRAIT_MODEL.disposition_for(DispositionId("risk_tolerance")).prior
        expected = risk_prior.alpha / (risk_prior.alpha + risk_prior.beta)
        assert snapshot.dispositions.risk_tolerance == pytest.approx(expected)

    def test_cold_start_has_zero_evidence(self) -> None:
        posterior = initial_posterior(TRAIT_MODEL)
        snapshot = project_effective_weights(posterior, TRAIT_MODEL)
        assert snapshot.total_weight_evidence_count == 0
        assert snapshot.total_disposition_evidence_count == 0


class TestOneObservation:
    """B. one observation moves the favoured factor's weight up, the other's down."""

    def test_favoured_factor_weight_increases_relative_to_cold_start(self) -> None:
        prior = initial_posterior(TRAIT_MODEL)
        cold_snapshot = project_effective_weights(prior, TRAIT_MODEL)

        obs = [PairwiseObservation(design={_FID_A: 1.0, _FID_B: -1.0}, outcome=1.0, weight=1.0)]
        updated = apply_pairwise_observations(prior, obs, DEFAULT_PREFERENCE_CONFIG)
        new_snapshot = project_effective_weights(updated, TRAIT_MODEL)

        assert new_snapshot.weights.weights[_FID_A] > cold_snapshot.weights.weights[_FID_A]
        assert new_snapshot.weights.weights[_FID_B] < cold_snapshot.weights.weights[_FID_B]


class TestRepeatedObservations:
    """C. repeated evidence moves the projection further than a single observation."""

    def test_five_repetitions_move_further_than_one(self) -> None:
        prior = initial_posterior(TRAIT_MODEL)
        obs = [PairwiseObservation(design={_FID_A: 1.0, _FID_B: -1.0}, outcome=1.0, weight=1.0)]

        once = project_effective_weights(
            apply_pairwise_observations(prior, obs, DEFAULT_PREFERENCE_CONFIG), TRAIT_MODEL
        )
        five_times = project_effective_weights(
            apply_pairwise_observations(prior, obs * 5, DEFAULT_PREFERENCE_CONFIG), TRAIT_MODEL
        )
        assert five_times.weights.weights[_FID_A] > once.weights.weights[_FID_A]


class TestContradictoryObservations:
    """D. contradictory evidence never produces NaN/infinite weights."""

    def test_ten_and_ten_opposing_observations_give_finite_weights(self) -> None:
        prior = initial_posterior(TRAIT_MODEL)
        a_over_b = PairwiseObservation(design={_FID_A: 1.0, _FID_B: -1.0}, outcome=1.0, weight=1.0)
        b_over_a = PairwiseObservation(design={_FID_A: 1.0, _FID_B: -1.0}, outcome=0.0, weight=1.0)
        updated = apply_pairwise_observations(
            prior, [a_over_b, b_over_a] * 10, DEFAULT_PREFERENCE_CONFIG
        )
        snapshot = project_effective_weights(updated, TRAIT_MODEL)
        for value in snapshot.weights.weights.values():
            assert math.isfinite(value)
        assert sum(snapshot.weights.weights.values()) == pytest.approx(1.0)


class TestSymmetry:
    """E. the M4 symmetric-pair fixture: identical priors + mirrored evidence -> equal weights."""

    def test_autonomy_and_stability_project_to_exactly_equal_weights(self) -> None:
        prior = initial_posterior(TRAIT_MODEL)
        assert prior.weights[_AUTONOMY].mu == prior.weights[_STABILITY].mu
        assert prior.weights[_AUTONOMY].sigma == prior.weights[_STABILITY].sigma

        observations = [
            PairwiseObservation(design={_AUTONOMY: 1.0, _STABILITY: -1.0}, outcome=1.0, weight=1.0),
            PairwiseObservation(design={_AUTONOMY: -1.0, _STABILITY: 1.0}, outcome=1.0, weight=1.0),
        ]
        updated = apply_pairwise_observations(prior, observations, DEFAULT_PREFERENCE_CONFIG)
        snapshot = project_effective_weights(updated, TRAIT_MODEL)
        assert snapshot.weights.weights[_AUTONOMY] == pytest.approx(
            snapshot.weights.weights[_STABILITY], abs=1e-12
        )


class TestColdStartEquality:
    """F. projection(prior) == declared prior-derived weights, via the same
    `softmax_over_known` function the engine itself uses (not re-derived by hand,
    since this test asserts *equality with the canonical transform*, not just a
    plausible-looking number)."""

    def test_matches_softmax_over_known_directly(self) -> None:
        posterior = initial_posterior(TRAIT_MODEL)
        snapshot = project_effective_weights(posterior, TRAIT_MODEL)
        expected = softmax_over_known(posterior.weights, TRAIT_MODEL.core_weight_factor_ids)
        assert snapshot.weights.weights == expected


class TestDeterminism:
    """G. repeated projection produces exactly equal results."""

    def test_repeated_projection_is_byte_identical(self) -> None:
        posterior = initial_posterior(TRAIT_MODEL)
        first = project_effective_weights(posterior, TRAIT_MODEL)
        second = project_effective_weights(posterior, TRAIT_MODEL)
        assert first.model_dump_json() == second.model_dump_json()


class TestImmutability:
    """H. the posterior is never mutated by projection."""

    def test_posterior_is_unchanged_after_projection(self) -> None:
        posterior = initial_posterior(TRAIT_MODEL)
        before = posterior.model_dump_json()
        project_effective_weights(posterior, TRAIT_MODEL)
        after = posterior.model_dump_json()
        assert before == after


class TestProvenance:
    """I. trait_schema_version / preference_engine_version / projection_version propagate."""

    def test_versions_are_propagated_correctly(self) -> None:
        posterior = initial_posterior(TRAIT_MODEL)
        snapshot = project_effective_weights(posterior, TRAIT_MODEL)
        assert snapshot.trait_schema_version == TRAIT_MODEL.version
        assert snapshot.preference_engine_version == posterior.engine_version
        assert snapshot.projection_version == PROJECTION_VERSION
        assert snapshot.read_transform == TRAIT_MODEL.read_transform

    def test_custom_projection_version_is_honoured(self) -> None:
        posterior = initial_posterior(TRAIT_MODEL)
        snapshot = project_effective_weights(posterior, TRAIT_MODEL, projection_version="2-test")
        assert snapshot.projection_version == "2-test"


class TestInvalidPosterior:
    """J. non-finite posterior values fail closed."""

    def test_nan_mu_fails_closed(self) -> None:
        posterior = initial_posterior(TRAIT_MODEL)
        weights = dict(posterior.weights)
        weights[_FID_A] = WeightPosterior.model_construct(factor=_FID_A, mu=math.nan, sigma=1.4)
        bad = posterior.model_copy(update={"weights": weights})
        with pytest.raises(PreferenceValidationError, match="non-finite"):
            project_effective_weights(bad, TRAIT_MODEL)

    def test_infinite_sigma_fails_closed(self) -> None:
        posterior = initial_posterior(TRAIT_MODEL)
        weights = dict(posterior.weights)
        weights[_FID_A] = WeightPosterior.model_construct(factor=_FID_A, mu=0.2, sigma=math.inf)
        bad = posterior.model_copy(update={"weights": weights})
        with pytest.raises(PreferenceValidationError, match="non-finite"):
            project_effective_weights(bad, TRAIT_MODEL)

    def test_nan_disposition_alpha_fails_closed(self) -> None:
        posterior = initial_posterior(TRAIT_MODEL)
        dispositions = dict(posterior.dispositions)
        target = DispositionId("risk_tolerance")
        dispositions[target] = DispositionPosterior.model_construct(
            id=target, alpha=math.nan, beta=2.0
        )
        bad = posterior.model_copy(update={"dispositions": dispositions})
        with pytest.raises(PreferenceValidationError, match="non-finite"):
            project_effective_weights(bad, TRAIT_MODEL)

    def test_missing_required_disposition_fails_closed(self) -> None:
        posterior = initial_posterior(TRAIT_MODEL)
        dispositions = dict(posterior.dispositions)
        del dispositions[DispositionId("risk_tolerance")]
        bad = posterior.model_copy(update={"dispositions": dispositions})
        with pytest.raises(PreferenceValidationError, match="missing a disposition posterior"):
            project_effective_weights(bad, TRAIT_MODEL)

    def test_missing_required_core_weight_fails_closed(self) -> None:
        posterior = initial_posterior(TRAIT_MODEL)
        weights = dict(posterior.weights)
        del weights[_FID_A]
        bad = posterior.model_copy(update={"weights": weights})
        with pytest.raises(PreferenceValidationError, match="missing a weight posterior"):
            project_effective_weights(bad, TRAIT_MODEL)


class TestSchemaMismatch:
    """K. an incompatible trait schema version fails explicitly."""

    def test_mismatched_trait_schema_version_fails_closed(self) -> None:
        posterior = initial_posterior(TRAIT_MODEL)
        bad = posterior.model_copy(update={"trait_schema_version": 999})
        with pytest.raises(PreferenceValidationError, match="trait_schema_version"):
            project_effective_weights(bad, TRAIT_MODEL)


class TestM3Compatibility:
    """L. the snapshot passes into decide() unmodified - MCDA math is untouched."""

    def test_snapshot_weights_and_dispositions_are_accepted_by_decide_unmodified(self) -> None:
        assert TAXONOMY.version == MCDA_TAXONOMY.version
        posterior = initial_posterior(TRAIT_MODEL)
        snapshot = project_effective_weights(posterior, TRAIT_MODEL)

        reading = FactorReading(known=True, level=ScaleLevel.HIGH)
        factors = FactorVector.from_items([(_FID_A, reading)])
        result = decide(MCDA_TAXONOMY, snapshot.weights, factors, snapshot.dispositions)
        assert result.score is not None  # decide() ran to completion with no adapter needed
