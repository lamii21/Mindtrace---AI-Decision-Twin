"""The Laplace/Newton weight update and the conjugate Beta disposition update.

The two tests ADR-005 names explicitly: `test_laplace_matches_gaussian_conjugate_posterior`
(atol 1e-8) and `test_beta_update_matches_closed_form`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import pytest

from mindtrace.domain.ids import DispositionId, FactorId
from mindtrace.domain.traits import (
    DispositionObservation,
    DispositionPosterior,
    PairwiseObservation,
    WeightPosterior,
)
from mindtrace.engines.preference.config import DEFAULT_PREFERENCE_CONFIG, PreferenceConfig
from mindtrace.engines.preference.update import (
    laplace_map_update,
    update_disposition,
    update_weights,
)

_FID_A = FactorId("skill_growth")
_FID_B = FactorId("financial_return")


class TestLaplaceMapUpdateVsGaussianConjugate:
    """ADR-005: "Laplace step on a Gaussian likelihood must equal the analytic
    conjugate posterior" - the Newton machinery itself, tested against a
    likelihood spec/04 never uses in production (a linear-Gaussian observation
    model), whose posterior has an exact closed form."""

    def test_matches_the_closed_form_bayesian_linear_regression_posterior(self) -> None:
        prior_mu = [0.3]
        prior_sigma = [1.5]
        sigma_obs = 0.8
        xs = [1.0, -0.5, 2.0, 0.75]
        ys = [0.9, -0.2, 1.8, 0.4]

        def grad_hess(theta: Sequence[float]) -> tuple[list[float], list[list[float]]]:
            residuals = [(y - theta[0] * x) for x, y in zip(xs, ys, strict=True)]
            grad = sum(r * x for r, x in zip(residuals, xs, strict=True)) / (sigma_obs**2)
            hess = -sum(x * x for x in xs) / (sigma_obs**2)
            return [grad], [[hess]]

        config = PreferenceConfig(sigma_floor=1e-9)
        mu, sigma = laplace_map_update(prior_mu, prior_sigma, grad_hess, config)

        prior_precision = 1.0 / prior_sigma[0] ** 2
        lik_precision = sum(x * x for x in xs) / sigma_obs**2
        posterior_precision = prior_precision + lik_precision
        posterior_variance = 1.0 / posterior_precision
        weighted_xy = sum(x * y for x, y in zip(xs, ys, strict=True)) / sigma_obs**2
        posterior_mean = posterior_variance * (prior_mu[0] * prior_precision + weighted_xy)
        posterior_sigma = math.sqrt(posterior_variance)

        assert mu[0] == pytest.approx(posterior_mean, abs=1e-8)
        assert sigma[0] == pytest.approx(posterior_sigma, abs=1e-8)

    def test_matches_the_closed_form_regardless_of_starting_prior_mean(self) -> None:
        # A purely quadratic log-posterior means Newton converges to the SAME mode
        # from any starting point - the closed form does not depend on prior_mu's
        # magnitude, only on how it enters the weighted average.
        xs = [1.0, 1.0, 1.0]
        ys = [2.0, 2.0, 2.0]
        sigma_obs = 1.0

        def grad_hess(theta: Sequence[float]) -> tuple[list[float], list[list[float]]]:
            residuals = [(y - theta[0] * x) for x, y in zip(xs, ys, strict=True)]
            grad = sum(r * x for r, x in zip(residuals, xs, strict=True)) / (sigma_obs**2)
            hess = -sum(x * x for x in xs) / (sigma_obs**2)
            return [grad], [[hess]]

        config = PreferenceConfig(sigma_floor=1e-9)
        for prior_mu in ([-10.0], [0.0], [50.0]):
            mu, _ = laplace_map_update(prior_mu, [1.5], grad_hess, config)
            prior_precision = 1.0 / 1.5**2
            lik_precision = sum(x * x for x in xs) / sigma_obs**2
            posterior_variance = 1.0 / (prior_precision + lik_precision)
            expected = posterior_variance * (
                prior_mu[0] * prior_precision + sum(x * y for x, y in zip(xs, ys, strict=True))
            )
            assert mu[0] == pytest.approx(expected, abs=1e-8)

    def test_multivariate_case_matches_a_diagonal_design_closed_form(self) -> None:
        # Orthogonal (diagonal) design: each dimension's posterior is independent,
        # so the diagonal-kept approximation is exact here too.
        prior_mu = [0.0, 0.0]
        prior_sigma = [1.0, 1.0]
        sigma_obs = 1.0
        # x1 = (1, 0), x2 = (0, 1) - orthogonal
        observations = [((1.0, 0.0), 2.0), ((0.0, 1.0), -1.0), ((1.0, 0.0), 2.0)]

        def grad_hess(theta: Sequence[float]) -> tuple[list[float], list[list[float]]]:
            grad = [0.0, 0.0]
            hess = [[0.0, 0.0], [0.0, 0.0]]
            for x, y in observations:
                pred = theta[0] * x[0] + theta[1] * x[1]
                residual = y - pred
                for i in range(2):
                    grad[i] += residual * x[i] / sigma_obs**2
                    for j in range(2):
                        hess[i][j] -= x[i] * x[j] / sigma_obs**2
            return grad, hess

        config = PreferenceConfig(sigma_floor=1e-9)
        mu, _ = laplace_map_update(prior_mu, prior_sigma, grad_hess, config)

        # dimension 0: two observations of y=2 with x=1
        prec0 = 1.0 + 2.0
        mean0 = (1.0 * 0.0 + 2.0 * 2.0) / prec0
        # dimension 1: one observation of y=-1 with x=1
        prec1 = 1.0 + 1.0
        mean1 = (1.0 * 0.0 + 1.0 * -1.0) / prec1

        assert mu[0] == pytest.approx(mean0, abs=1e-8)
        assert mu[1] == pytest.approx(mean1, abs=1e-8)


class TestBetaUpdateVsClosedForm:
    def test_matches_the_pseudo_count_closed_form(self) -> None:
        prior = DispositionPosterior(id=DispositionId("risk_tolerance"), alpha=2.0, beta=2.0)
        observation = DispositionObservation(target=DispositionId("risk_tolerance"), outcome=1.0)
        config = PreferenceConfig(pseudocount_kappa=1.5)
        updated = update_disposition(prior, observation, config)
        assert updated.alpha == pytest.approx(2.0 + 1.5 * 1.0)
        assert updated.beta == pytest.approx(2.0 + 1.5 * 0.0)

    def test_indifferent_outcome_splits_the_pseudocount_evenly(self) -> None:
        prior = DispositionPosterior(id=DispositionId("risk_tolerance"), alpha=2.0, beta=2.0)
        observation = DispositionObservation(target=DispositionId("risk_tolerance"), outcome=0.5)
        config = PreferenceConfig(pseudocount_kappa=1.5)
        updated = update_disposition(prior, observation, config)
        assert updated.alpha == pytest.approx(2.0 + 0.75)
        assert updated.beta == pytest.approx(2.0 + 0.75)

    def test_repeated_updates_accumulate(self) -> None:
        prior = DispositionPosterior(id=DispositionId("risk_tolerance"), alpha=2.0, beta=2.0)
        config = PreferenceConfig(pseudocount_kappa=1.5)
        observation = DispositionObservation(target=DispositionId("risk_tolerance"), outcome=1.0)
        updated = prior
        for _ in range(3):
            updated = update_disposition(updated, observation, config)
        assert updated.alpha == pytest.approx(2.0 + 3 * 1.5)
        assert updated.beta == pytest.approx(2.0)


class TestUpdateWeightsProperties:
    def test_empty_observations_return_the_prior_unchanged(self) -> None:
        prior = {_FID_A: WeightPosterior(factor=_FID_A, mu=0.1, sigma=1.4)}
        result = update_weights(prior, [], DEFAULT_PREFERENCE_CONFIG)
        assert result[_FID_A].mu == prior[_FID_A].mu
        assert result[_FID_A].sigma == prior[_FID_A].sigma

    def test_mean_zero_gauge_holds_after_update(self) -> None:
        prior = {
            _FID_A: WeightPosterior(factor=_FID_A, mu=0.1, sigma=1.4),
            _FID_B: WeightPosterior(factor=_FID_B, mu=-0.1, sigma=1.4),
            FactorId("autonomy"): WeightPosterior(factor=FactorId("autonomy"), mu=0.0, sigma=1.5),
        }
        observations = [
            PairwiseObservation(design={_FID_A: 1.0, _FID_B: -1.0}, outcome=1.0, weight=1.0)
        ]
        result = update_weights(prior, observations, DEFAULT_PREFERENCE_CONFIG)
        assert sum(w.mu for w in result.values()) == pytest.approx(0.0, abs=1e-9)

    def test_sigma_never_falls_below_the_configured_floor(self) -> None:
        prior = {_FID_A: WeightPosterior(factor=_FID_A, mu=0.0, sigma=1.4)}
        # Extreme, repeated, perfectly-separating evidence.
        observations = [
            PairwiseObservation(design={_FID_A: 5.0}, outcome=1.0, weight=1.0) for _ in range(50)
        ]
        config = PreferenceConfig(sigma_floor=0.2)
        result = update_weights(prior, observations, config)
        assert result[_FID_A].sigma >= 0.2

    def test_monotone_evidence_never_decreases_the_favoured_factors_mu(self) -> None:
        prior = {
            _FID_A: WeightPosterior(factor=_FID_A, mu=0.0, sigma=1.4),
            _FID_B: WeightPosterior(factor=_FID_B, mu=0.0, sigma=1.4),
        }
        observations = [
            PairwiseObservation(design={_FID_A: 1.0, _FID_B: -1.0}, outcome=1.0, weight=1.0)
        ]
        result = update_weights(prior, observations, DEFAULT_PREFERENCE_CONFIG)
        assert result[_FID_A].mu > prior[_FID_A].mu
        assert result[_FID_B].mu < prior[_FID_B].mu
