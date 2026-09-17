"""Deterministic posterior updates: Laplace/Newton (weights) and conjugate Beta (dispositions).

Spec/04 §3: no conjugacy for the logistic Bradley-Terry link, so weights are
updated via a fixed, damped Newton-Raphson MAP estimate followed by a
diagonal, observed-Fisher-information posterior variance (the marginal-
independence simplification ADR-005 accepts for v1). Dispositions use the
exact conjugate Beta pseudo-count update (spec/04 §3, spec/07 §4.2) - no
approximation needed there at all.

``laplace_map_update`` is the generic numerical engine: it takes any
per-observation log-*likelihood* gradient/Hessian function and adds the
Gaussian prior itself. ``update_weights`` is its Bradley-Terry-specific
production caller. Keeping them separate is what lets the test suite verify
the Newton machinery against an exactly-conjugate Gaussian-linear likelihood
(ADR-005's own required test: "Laplace step on a Gaussian likelihood must
equal the analytic conjugate posterior") without a fake "Gaussian mode"
ever existing in production code.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from mindtrace.domain.ids import DispositionId, FactorId
from mindtrace.domain.traits import (
    DispositionObservation,
    DispositionPosterior,
    PairwiseObservation,
    PreferencePosterior,
    WeightPosterior,
)
from mindtrace.engines.preference._linalg import solve
from mindtrace.engines.preference._numeric import stable_sigmoid
from mindtrace.engines.preference.config import DEFAULT_PREFERENCE_CONFIG, PreferenceConfig

GradHessFn = Callable[[Sequence[float]], tuple[list[float], list[list[float]]]]


def laplace_map_update(
    prior_mu: Sequence[float],
    prior_sigma: Sequence[float],
    log_likelihood_grad_hess: GradHessFn,
    config: PreferenceConfig,
) -> tuple[list[float], list[float]]:
    """`(mu_map, sigma_post)` via `config.newton_steps` fixed, damped Newton iterations.

    `log_likelihood_grad_hess(theta)` returns the *likelihood's own* gradient
    and Hessian (never including the prior) at `theta`; this function adds
    the diagonal Gaussian prior's contribution at every step, per spec/04 §3:
    start from `Normal(mu, Sigma)`, run `N` damped Newton steps on
    `log P(obs | theta) + log Prior(theta)`, then read the diagonal of the
    observed Fisher information for the posterior variance.
    """
    n = len(prior_mu)
    prior_precision = [1.0 / (sigma * sigma) for sigma in prior_sigma]
    theta = list(prior_mu)

    for _ in range(config.newton_steps):
        grad_lik, hess_lik = log_likelihood_grad_hess(theta)
        grad = [grad_lik[i] - prior_precision[i] * (theta[i] - prior_mu[i]) for i in range(n)]
        neg_hess = [[-hess_lik[i][j] for j in range(n)] for i in range(n)]
        for i in range(n):
            neg_hess[i][i] += prior_precision[i]
        delta = solve(neg_hess, grad)
        theta = [theta[i] + config.newton_damping * delta[i] for i in range(n)]

    _, hess_lik_final = log_likelihood_grad_hess(theta)
    posterior_sigma = []
    for i in range(n):
        observed_fisher_i = -hess_lik_final[i][i]
        precision_i = prior_precision[i] + observed_fisher_i
        sigma_i = (1.0 / precision_i) ** 0.5 if precision_i > 0 else prior_sigma[i]
        posterior_sigma.append(max(sigma_i, config.sigma_floor))

    return theta, posterior_sigma


def _bradley_terry_grad_hess_fn(
    factor_order: Sequence[FactorId],
    observations: Sequence[PairwiseObservation],
    scale_s: float,
) -> GradHessFn:
    """Spec/04 §3's pairwise likelihood: `P(A>B|theta) = sigma((1/s) * theta . x)`."""
    n = len(factor_order)
    design_vectors = [[obs.design.get(fid, 0.0) for fid in factor_order] for obs in observations]

    def grad_hess(theta: Sequence[float]) -> tuple[list[float], list[list[float]]]:
        grad = [0.0] * n
        hess = [[0.0] * n for _ in range(n)]
        for obs, x in zip(observations, design_vectors, strict=True):
            eta = sum(theta[i] * x[i] for i in range(n)) / scale_s
            p = stable_sigmoid(eta)
            coef_grad = obs.weight * (obs.outcome - p) / scale_s
            coef_hess = obs.weight * p * (1.0 - p) / (scale_s * scale_s)
            for i in range(n):
                if x[i] == 0.0:
                    continue
                grad[i] += coef_grad * x[i]
                row = hess[i]
                for j in range(n):
                    if x[j] == 0.0:
                        continue
                    row[j] -= coef_hess * x[i] * x[j]
        return grad, hess

    return grad_hess


def update_weights(
    prior: Mapping[FactorId, WeightPosterior],
    observations: Sequence[PairwiseObservation],
    config: PreferenceConfig,
) -> dict[FactorId, WeightPosterior]:
    """The production Bradley-Terry Laplace update (spec/04 §3, spec/07 §4.1).

    Re-imposes the mean-zero gauge (spec/04 §2) across *every* weight, not
    only ones an observation touched - `softmax` is only ever meaningful up
    to a shared additive constant. Returns the prior unchanged (a fresh dict
    with identical values) when `observations` is empty: no evidence, no move.
    """
    factor_order = sorted(prior)
    if not observations:
        return dict(prior)

    prior_mu = [prior[fid].mu for fid in factor_order]
    prior_sigma = [prior[fid].sigma for fid in factor_order]
    grad_hess_fn = _bradley_terry_grad_hess_fn(factor_order, observations, config.logistic_scale_s)
    mu, sigma = laplace_map_update(prior_mu, prior_sigma, grad_hess_fn, config)

    gauge_shift = sum(mu) / len(mu)
    mu = [value - gauge_shift for value in mu]

    return {
        fid: WeightPosterior(factor=fid, mu=mu[i], sigma=sigma[i])
        for i, fid in enumerate(factor_order)
    }


def update_disposition(
    prior: DispositionPosterior,
    observation: DispositionObservation,
    config: PreferenceConfig,
) -> DispositionPosterior:
    """The exact conjugate update (spec/04 §3, spec/07 §4.2).

    `alpha += kappa*y_eff`, `beta += kappa*(1-y_eff)`.
    """
    kappa = config.pseudocount_kappa
    return DispositionPosterior(
        id=prior.id,
        alpha=prior.alpha + kappa * observation.outcome,
        beta=prior.beta + kappa * (1.0 - observation.outcome),
    )


def update_dispositions(
    prior: Mapping[DispositionId, DispositionPosterior],
    observations: Sequence[DispositionObservation],
    config: PreferenceConfig,
) -> dict[DispositionId, DispositionPosterior]:
    """Fold `update_disposition` over `observations`, one target at a time, in order given."""
    posterior = dict(prior)
    for observation in observations:
        posterior[observation.target] = update_disposition(
            posterior[observation.target], observation, config
        )
    return posterior


def _touched_factors(observations: Sequence[PairwiseObservation]) -> set[FactorId]:
    touched: set[FactorId] = set()
    for observation in observations:
        touched.update(fid for fid, value in observation.design.items() if value != 0.0)
    return touched


def apply_pairwise_observations(
    posterior: PreferencePosterior,
    observations: Sequence[PairwiseObservation],
    config: PreferenceConfig = DEFAULT_PREFERENCE_CONFIG,
) -> PreferencePosterior:
    """One batch Laplace pass over `observations`.

    Spec/07 §4.1: "accumulates all (x_k, y_k, weight_k) and, at the end, runs
    one Laplace pass" - never incremental per item, so Laplace approximation
    error never compounds. Bumps `weight_evidence_count` by one for every
    factor any observation actually varies; a factor untouched by this batch
    keeps its count.
    """
    new_weights = update_weights(posterior.weights, observations, config)
    new_counts = dict(posterior.weight_evidence_count)
    for factor_id in _touched_factors(observations):
        new_counts[factor_id] = new_counts.get(factor_id, 0) + 1
    return posterior.model_copy(
        update={"weights": new_weights, "weight_evidence_count": new_counts}
    )


def apply_disposition_observations(
    posterior: PreferencePosterior,
    observations: Sequence[DispositionObservation],
    config: PreferenceConfig = DEFAULT_PREFERENCE_CONFIG,
) -> PreferencePosterior:
    """Apply each disposition observation's conjugate update and bump its evidence count."""
    new_dispositions = update_dispositions(posterior.dispositions, observations, config)
    new_counts = dict(posterior.disposition_evidence_count)
    for observation in observations:
        new_counts[observation.target] = new_counts.get(observation.target, 0) + 1
    return posterior.model_copy(
        update={"dispositions": new_dispositions, "disposition_evidence_count": new_counts}
    )
