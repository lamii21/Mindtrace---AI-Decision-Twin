"""Property-based tests for the preference engine (M4 s21).

Every property here is one the mathematics actually guarantees for THIS
engine's design (a single batch Laplace pass, not incremental updates) - not
a property that merely "seems to usually hold". Where floating-point
non-associativity could in principle perturb a bit-exact equality (e.g.
order-invariance, which is only guaranteed up to summation order), the test
uses a tight numerical tolerance instead of exact equality, and says why.
"""

from __future__ import annotations

import math
import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mindtrace.domain.ids import DispositionId, FactorId
from mindtrace.domain.traits import DispositionObservation, PairwiseObservation, WeightPosterior
from mindtrace.engines.preference.config import DEFAULT_PREFERENCE_CONFIG
from mindtrace.engines.preference.posterior import disposition_value
from mindtrace.engines.preference.prior import initial_posterior
from mindtrace.engines.preference.update import (
    apply_disposition_observations,
    apply_pairwise_observations,
    update_weights,
)
from tests.support.preference_fixtures import TRAIT_MODEL

_FID_A = FactorId("skill_growth")
_FID_B = FactorId("financial_return")

_SYNTHETIC_FACTORS = tuple(FactorId(f"f{i}") for i in range(4))


def _synthetic_prior(mu: float = 0.0, sigma: float = 1.4) -> dict[FactorId, WeightPosterior]:
    return {fid: WeightPosterior(factor=fid, mu=mu, sigma=sigma) for fid in _SYNTHETIC_FACTORS}


_outcome_strategy = st.sampled_from([0.0, 0.5, 1.0])
_weight_strategy = st.sampled_from([0.5, 1.0])


_factor_pair_strategy = st.lists(
    st.sampled_from(_SYNTHETIC_FACTORS), min_size=2, max_size=2, unique=True
)


@st.composite
def pairwise_observations(
    draw: st.DrawFn, *, min_size: int = 1, max_size: int = 6
) -> list[PairwiseObservation]:
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    observations = []
    for _ in range(n):
        a, b = draw(_factor_pair_strategy)
        design = {a: 1.0, b: -1.0}
        outcome = draw(_outcome_strategy)
        weight = draw(_weight_strategy)
        observations.append(PairwiseObservation(design=design, outcome=outcome, weight=weight))
    return observations


class TestDeterminism:
    @given(observations=pairwise_observations())
    @settings(max_examples=100)
    def test_same_observations_give_identical_posterior(
        self, observations: list[PairwiseObservation]
    ) -> None:
        prior = _synthetic_prior()
        first = update_weights(prior, observations, DEFAULT_PREFERENCE_CONFIG)
        second = update_weights(prior, observations, DEFAULT_PREFERENCE_CONFIG)
        for fid in _SYNTHETIC_FACTORS:
            assert first[fid].mu == second[fid].mu
            assert first[fid].sigma == second[fid].sigma


class TestOrderInvariance:
    @given(observations=pairwise_observations(min_size=2))
    @settings(max_examples=50)
    def test_shuffled_batch_gives_the_same_posterior(
        self, observations: list[PairwiseObservation]
    ) -> None:
        """A single batch Laplace pass sums every observation's gradient/Hessian
        contribution - commutative addition, so the mathematical result does not
        depend on list order (unlike an incremental per-item update, which spec/07
        s4.1 explicitly rejects: "Laplace error accumulates"). Floating-point
        addition is not perfectly associative, so this asserts near-equality
        rather than bit-exact equality."""
        prior = _synthetic_prior()
        shuffled = observations[:]
        random.Random(0).shuffle(shuffled)

        original = update_weights(prior, observations, DEFAULT_PREFERENCE_CONFIG)
        reordered = update_weights(prior, shuffled, DEFAULT_PREFERENCE_CONFIG)

        for fid in _SYNTHETIC_FACTORS:
            assert math.isclose(original[fid].mu, reordered[fid].mu, abs_tol=1e-6)
            assert math.isclose(original[fid].sigma, reordered[fid].sigma, abs_tol=1e-6)


class TestNoEvidence:
    @given(
        mu=st.floats(min_value=-2.0, max_value=2.0),
        sigma=st.floats(min_value=0.5, max_value=3.0),
    )
    @settings(max_examples=50)
    def test_empty_observations_leave_the_prior_untouched(self, mu: float, sigma: float) -> None:
        prior = _synthetic_prior(mu=mu, sigma=sigma)
        result = update_weights(prior, [], DEFAULT_PREFERENCE_CONFIG)
        for fid in _SYNTHETIC_FACTORS:
            assert result[fid].mu == prior[fid].mu
            assert result[fid].sigma == prior[fid].sigma


class TestRepeatedEvidence:
    @given(n=st.integers(min_value=1, max_value=8))
    @settings(max_examples=30)
    def test_more_repetitions_move_the_favoured_factor_further_and_narrower(self, n: int) -> None:
        prior = _synthetic_prior()
        fid_a, fid_b = _SYNTHETIC_FACTORS[0], _SYNTHETIC_FACTORS[1]
        one_obs = [PairwiseObservation(design={fid_a: 1.0, fid_b: -1.0}, outcome=1.0, weight=1.0)]
        many_obs = one_obs * n

        one_result = update_weights(prior, one_obs, DEFAULT_PREFERENCE_CONFIG)
        many_result = update_weights(prior, many_obs, DEFAULT_PREFERENCE_CONFIG)

        if n > 1:
            assert many_result[fid_a].mu >= one_result[fid_a].mu
            assert many_result[fid_a].sigma <= one_result[fid_a].sigma


class TestSymmetry:
    @given(observations=pairwise_observations())
    @settings(max_examples=50)
    def test_a_perfectly_mirrored_evidence_set_keeps_symmetric_factors_equal(
        self, observations: list[PairwiseObservation]
    ) -> None:
        """Every observation and its design-negated counterpart (same `outcome`),
        both present with equal weight, keep every factor's posterior at 0.

        The combined log-likelihood is invariant under a *global* sign flip
        `theta -> -theta` (each `(x, y)`/`(-x, y)` pair contributes identically
        under that flip), and the i.i.d. zero-mean Gaussian prior is too - so
        the (unique, by concavity) MAP is exactly `theta = 0` for every trait,
        regardless of which pairs the random observations touched.
        """
        prior = _synthetic_prior()
        mirrored: list[PairwiseObservation] = []
        for obs in observations:
            mirrored.append(obs)
            flipped_design = {fid: -value for fid, value in obs.design.items()}
            mirrored.append(
                PairwiseObservation(design=flipped_design, outcome=obs.outcome, weight=obs.weight)
            )
        result = update_weights(prior, mirrored, DEFAULT_PREFERENCE_CONFIG)
        for fid in _SYNTHETIC_FACTORS:
            assert result[fid].mu == pytest.approx(0.0, abs=1e-9)


class TestContradiction:
    def test_equal_and_opposite_observations_cancel_the_mean_but_still_narrow_sigma(self) -> None:
        """Contradictory evidence is not discarded (sigma still shrinks, evidence_count
        still counts both), but for a zero-mean-prior single pair its net effect on
        `mu` is exactly zero - the log-posterior is symmetric under theta -> -theta
        when the two observations' outcomes are exact complements."""
        prior = _synthetic_prior(mu=0.0)
        fid_a, fid_b = _SYNTHETIC_FACTORS[0], _SYNTHETIC_FACTORS[1]
        contradictory = [
            PairwiseObservation(design={fid_a: 1.0, fid_b: -1.0}, outcome=1.0, weight=1.0),
            PairwiseObservation(design={fid_a: 1.0, fid_b: -1.0}, outcome=0.0, weight=1.0),
        ]
        result = update_weights(prior, contradictory, DEFAULT_PREFERENCE_CONFIG)
        assert result[fid_a].mu == pytest.approx(prior[fid_a].mu, abs=1e-9)
        assert result[fid_a].sigma < prior[fid_a].sigma

    def test_posterior_evidence_count_reflects_every_observation_not_a_net_zero(self) -> None:
        posterior = initial_posterior(TRAIT_MODEL)
        contradictory = [
            PairwiseObservation(design={_FID_A: 1.0, _FID_B: -1.0}, outcome=1.0, weight=1.0),
            PairwiseObservation(design={_FID_A: 1.0, _FID_B: -1.0}, outcome=0.0, weight=1.0),
        ]
        updated = apply_pairwise_observations(posterior, contradictory, DEFAULT_PREFERENCE_CONFIG)
        # Both observations touched A and B - the count reflects that a batch
        # touched them, not that the two observations "cancelled out" of history.
        assert updated.weight_evidence_count[_FID_A] == posterior.weight_evidence_count[_FID_A] + 1
        assert updated.weight_evidence_count[_FID_B] == posterior.weight_evidence_count[_FID_B] + 1


class TestDispositionProperties:
    @given(y=st.floats(min_value=0.0, max_value=1.0), n=st.integers(min_value=0, max_value=5))
    @settings(max_examples=30)
    def test_repeated_consistent_disposition_evidence_moves_value_monotonically(
        self, y: float, n: int
    ) -> None:
        posterior = initial_posterior(TRAIT_MODEL)
        target = DispositionId("risk_tolerance")
        observations = [DispositionObservation(target=target, outcome=y)] * n
        updated = apply_disposition_observations(posterior, observations, DEFAULT_PREFERENCE_CONFIG)

        prior_value = disposition_value(posterior.dispositions[target])
        new_value = disposition_value(updated.dispositions[target])
        if n == 0:
            assert new_value == prior_value
        elif y > 0.5:
            assert new_value >= prior_value
        elif y < 0.5:
            assert new_value <= prior_value
