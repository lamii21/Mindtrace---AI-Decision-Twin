"""Posterior read-side: `value`/`confidence`/`credible_interval` (spec/04 §5).

Also two bridges to engines that already exist - `effective_sample_sizes`
(into `mindtrace.engines.confidence`'s `evidence_sufficiency`, spec/06 §4.1)
and `to_disposition_inputs` (into `mindtrace.engines.mcda`'s
`DispositionInputs`, M3). Neither bridge changes the engine it feeds: both
simply reshape this engine's own posterior into the exact input shape the
other engine already accepts.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from mindtrace.domain.decision import DispositionInputs
from mindtrace.domain.ids import DispositionId, FactorId
from mindtrace.domain.traits import (
    CredibleInterval,
    DispositionPosterior,
    TraitModel,
    TraitReport,
    WeightPosterior,
)
from mindtrace.engines.preference._numeric import clamp

_Z_90 = 1.6448536269514722  # two-sided 90% normal critical value (spec/04 §5, §3: "central 90%")
_PRIOR_BETA_SD = math.sqrt((2.0 * 2.0) / ((2.0 + 2.0) ** 2 * (2.0 + 2.0 + 1.0)))  # sd(Beta(2,2))


def softmax_over_known(
    weights: Mapping[FactorId, WeightPosterior], known_ids: Sequence[FactorId]
) -> dict[FactorId, float]:
    """`w_i = softmax(theta)_i` restricted to `known_ids`.

    Per `traits.yaml`'s `read_transform: softmax_over_known`. Empty
    `known_ids` gives an empty result - never a division by zero.
    """
    if not known_ids:
        return {}
    mus = [weights[fid].mu for fid in known_ids]
    shift = max(mus)
    exponentials = [math.exp(mu - shift) for mu in mus]
    total = sum(exponentials)
    return dict(zip(known_ids, (value / total for value in exponentials), strict=True))


def weight_confidence(posterior: WeightPosterior, prior_sigma: float) -> float:
    """`clip(sqrt(1 - sigma_post/sigma_prior), 0, 1)` (spec/04 §5).

    "How much has evidence narrowed this trait relative to the prior."
    """
    ratio = posterior.sigma / prior_sigma
    return clamp(math.sqrt(max(0.0, 1.0 - ratio)), 0.0, 1.0)


def weight_credible_interval(
    weights: Mapping[FactorId, WeightPosterior],
    known_ids: Sequence[FactorId],
    factor_id: FactorId,
) -> CredibleInterval:
    """Perturb `factor_id`'s logit by +-z*sigma and re-apply `softmax_over_known`.

    Every other known trait is held at its posterior mean. Spec/04 §5
    defines the transform for `value` (posterior mean -> softmax)
    but not for the interval's own units; reporting a logit-scale interval
    next to a probability-scale `value` would be internally inconsistent, so
    this single-trait-perturbation procedure is this engine's explicit,
    documented interpretation (M4 final report, Deviations).
    """
    posterior = weights[factor_id]
    half_width = _Z_90 * posterior.sigma
    low_weights = dict(weights)
    high_weights = dict(weights)
    low_weights[factor_id] = posterior.model_copy(update={"mu": posterior.mu - half_width})
    high_weights[factor_id] = posterior.model_copy(update={"mu": posterior.mu + half_width})
    low = softmax_over_known(low_weights, known_ids)[factor_id]
    high = softmax_over_known(high_weights, known_ids)[factor_id]
    return CredibleInterval(low=min(low, high), high=max(low, high))


def weight_report(
    weights: Mapping[FactorId, WeightPosterior],
    known_ids: Sequence[FactorId],
    factor_id: FactorId,
    trait_model: TraitModel,
    evidence_count: int,
) -> TraitReport:
    """The full `TraitReport` (spec/04 §5) for one importance weight, over `known_ids`."""
    values = softmax_over_known(weights, known_ids)
    prior_sigma = trait_model.weight_for(factor_id).prior.sigma
    confidence = weight_confidence(weights[factor_id], prior_sigma)
    ci = weight_credible_interval(weights, known_ids, factor_id)
    source = (
        "inferred" if evidence_count >= trait_model.report.min_evidence_for_inferred else "declared"
    )
    return TraitReport(
        id=str(factor_id),
        value=values[factor_id],
        confidence=confidence,
        credible_interval=ci,
        evidence_count=evidence_count,
        source=source,
    )


def effective_sample_sizes(
    weights: Mapping[FactorId, WeightPosterior], trait_model: TraitModel
) -> dict[FactorId, float]:
    """`N_eff_i = clamp(sigma_prior^2 / sigma_post_i^2 - 1, 0, inf)` (spec/06 §4.1).

    Exactly the shape `mindtrace.engines.confidence.evidence.evidence_sufficiency`'s
    `n_eff` parameter already expects - a drop-in bridge, zero changes to the
    confidence engine's interface.
    """
    result: dict[FactorId, float] = {}
    for factor_id, posterior in weights.items():
        prior_sigma = trait_model.weight_for(factor_id).prior.sigma
        ratio = (prior_sigma * prior_sigma) / (posterior.sigma * posterior.sigma)
        result[factor_id] = max(0.0, ratio - 1.0)
    return result


def disposition_value(posterior: DispositionPosterior) -> float:
    """The Beta posterior mean: `alpha / (alpha + beta)`."""
    return posterior.alpha / (posterior.alpha + posterior.beta)


def _beta_sd(alpha: float, beta: float) -> float:
    total = alpha + beta
    return math.sqrt((alpha * beta) / (total * total * (total + 1.0)))


def disposition_confidence(posterior: DispositionPosterior) -> float:
    """`clip(1 - sd(Beta(a,b)) / sd(Beta(2,2)), 0, 1)` (spec/04 §5)."""
    sd = _beta_sd(posterior.alpha, posterior.beta)
    return clamp(1.0 - sd / _PRIOR_BETA_SD, 0.0, 1.0)


def disposition_credible_interval(posterior: DispositionPosterior) -> CredibleInterval:
    """Normal approximation to the `Beta(alpha, beta)` marginal's central 90% interval.

    The standard library has no Beta-quantile function and this engine adds
    no numerical dependency (see `_linalg.py`); `alpha`/`beta` only ever grow
    from their `traits.yaml` priors (both >= 2), where the normal
    approximation to a Beta distribution is a standard, well-behaved
    approximation. Documented explicitly as an approximation (M4 final
    report, Deviations), not claimed as exact.
    """
    mean = disposition_value(posterior)
    sd = _beta_sd(posterior.alpha, posterior.beta)
    half_width = _Z_90 * sd
    return CredibleInterval(
        low=clamp(mean - half_width, 0.0, 1.0),
        high=clamp(mean + half_width, 0.0, 1.0),
    )


def disposition_report(
    posterior: DispositionPosterior,
    trait_model: TraitModel,
    evidence_count: int,
) -> TraitReport:
    """The full `TraitReport` (spec/04 §5) for one disposition."""
    source = (
        "inferred" if evidence_count >= trait_model.report.min_evidence_for_inferred else "declared"
    )
    return TraitReport(
        id=str(posterior.id),
        value=disposition_value(posterior),
        confidence=disposition_confidence(posterior),
        credible_interval=disposition_credible_interval(posterior),
        evidence_count=evidence_count,
        source=source,
    )


def to_disposition_inputs(
    dispositions: Mapping[DispositionId, DispositionPosterior],
) -> DispositionInputs:
    """Posterior Beta means -> M3's `DispositionInputs` (spec/04 §4's mechanical-effect table).

    M3 already implements the mechanical link itself; this only reads means -
    the "thin adapter" between the two engines, no MCDA mathematics touched.
    """
    return DispositionInputs(
        risk_tolerance=disposition_value(dispositions[DispositionId("risk_tolerance")]),
        time_discount=disposition_value(dispositions[DispositionId("time_discount")]),
        ambiguity_aversion=disposition_value(dispositions[DispositionId("ambiguity_aversion")]),
        effort_tolerance=disposition_value(dispositions[DispositionId("effort_tolerance")]),
    )
