"""Deterministic re-parametrisation of the MCDA engine per twin (M10; ADR-007 decision).

``w_t = renorm(w* . (1 + lambda . shift_t))`` - a bounded, named, fixed shift
of the user's own base effective weight vector, applied once per declared
twin (``schema/twins.yaml``). No twin has a different prompt, a different
code path, or an LLM personality: :func:`run_twin_ensemble` calls
``engines.mcda.decide`` exactly once per twin, with the same taxonomy, the
same extracted factors, and the same dispositions - only ``weights`` differs.
"""

from __future__ import annotations

from collections.abc import Sequence

from mindtrace.domain.confidence import EnsembleObservation
from mindtrace.domain.decision import DispositionInputs, FactorVector, WeightVector
from mindtrace.domain.factors import FactorTaxonomy
from mindtrace.domain.ids import FactorId
from mindtrace.domain.simulation import TwinConfigResult
from mindtrace.domain.traits import EffectiveWeightVector
from mindtrace.domain.twins import BASE_TWIN_ID, TwinDefinition
from mindtrace.engines.mcda.config import DEFAULT_MCDA_CONFIG, MCDAConfig
from mindtrace.engines.mcda.decide import decide


def apply_twin_transform(
    base_weights: WeightVector, twin: TwinDefinition, *, lam: float
) -> WeightVector:
    """``renorm(w* . (1 + lambda . shift_t))`` - ``shift_t`` is +1/-1/0 per factor (ADR-007).

    Every factor named in ``twin.up`` is multiplied by ``(1 + lam)``, every
    factor in ``twin.down`` by ``(1 - lam)``, every other factor is left at
    ``w*`` exactly - then the whole vector is renormalised to sum to 1.
    ``WeightVector``'s own validator (non-negative, sums to 1) re-checks the
    result; it is never bypassed.
    """
    raw: dict[FactorId, float] = {}
    for factor_id, weight in base_weights.weights.items():
        if factor_id in twin.up:
            raw[factor_id] = weight * (1.0 + lam)
        elif factor_id in twin.down:
            raw[factor_id] = weight * (1.0 - lam)
        else:
            raw[factor_id] = weight
    total = sum(raw.values())
    normalized = {factor_id: value / total for factor_id, value in raw.items()}
    return WeightVector(weights=normalized)


def run_twin_ensemble(
    taxonomy: FactorTaxonomy,
    base_preference: EffectiveWeightVector,
    base_decision: TwinConfigResult,
    twins: Sequence[TwinDefinition],
    factors_a: FactorVector,
    *,
    factors_b: FactorVector | None = None,
    lam: float,
    mcda_config: MCDAConfig = DEFAULT_MCDA_CONFIG,
) -> tuple[TwinConfigResult, ...]:
    """Run ``decide()`` once per twin (plus the already-computed base) over the same factors.

    ``base_decision`` is the base twin's own already-computed
    ``TwinConfigResult`` (``twin == "base"``) - never recomputed here, so the
    base twin's result is always byte-identical to calling
    ``engines.mcda.decide`` directly with ``base_preference.weights`` (the
    single-twin-compatibility guarantee, M10 planning).
    """
    if base_decision.twin != BASE_TWIN_ID:
        msg = f"base_decision.twin must be {BASE_TWIN_ID!r}, got {base_decision.twin!r}"
        raise ValueError(msg)

    results = [base_decision]
    dispositions: DispositionInputs = base_preference.dispositions
    for twin in twins:
        transformed_weights = apply_twin_transform(base_preference.weights, twin, lam=lam)
        decision = decide(
            taxonomy,
            transformed_weights,
            factors_a,
            dispositions,
            factors_b=factors_b,
            config=mcda_config,
        )
        preference = base_preference.model_copy(update={"weights": transformed_weights})
        results.append(TwinConfigResult(twin=twin.id, preference=preference, decision=decision))
    return tuple(results)


def ensemble_observation_from(twin_results: Sequence[TwinConfigResult]) -> EnsembleObservation:
    """Project the twins' scores/labels into the ``EnsembleObservation`` M4 already consumes.

    A projection, not a computation - ``engines.confidence.ensemble.
    ensemble_term`` owns the dispersion/degenerate-guard math untouched.
    """
    return EnsembleObservation(
        scores=tuple(result.decision.score for result in twin_results),
        labels=tuple(result.decision.label for result in twin_results),
    )


__all__ = ["apply_twin_transform", "ensemble_observation_from", "run_twin_ensemble"]
