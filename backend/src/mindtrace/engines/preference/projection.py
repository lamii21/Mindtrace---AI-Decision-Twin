"""`PreferencePosterior -> EffectiveWeightVector` (M6-A).

The one authoritative posterior-to-MCDA-weight projection. No new
mathematics: `softmax_over_known` (`posterior.py`, already M4's own
canonical read-time transform - `traits.yaml`'s own `read_transform:
softmax_over_known`) projects the weight posteriors' means, and
`to_disposition_inputs` (`posterior.py`, already M4's own bridge to M3's
`DispositionInputs`) projects the disposition posteriors' means. Both
functions already exist and are already tested; this module only composes
them and adds the schema/finiteness checks a posterior alone doesn't
guarantee, plus provenance.

M3's own known-set weight renormalization (spec/05 §2c) is untouched and not
duplicated here: it still runs *inside* `decide()`, per decision, over
whichever factors that particular scenario happens to know. A twin-level
weight vector has no "known set" of its own - `EffectiveWeightVector.weights`
is the twin's full raw importance weights over every core factor (exactly
what `decide()` already expects as input), not a pre-renormalized subset.
"""

from __future__ import annotations

import math

from mindtrace.domain.decision import WeightVector
from mindtrace.domain.ids import DispositionId
from mindtrace.domain.traits import EffectiveWeightVector, PreferencePosterior, TraitModel
from mindtrace.engines.preference.config import PROJECTION_VERSION
from mindtrace.engines.preference.errors import PreferenceValidationError
from mindtrace.engines.preference.posterior import softmax_over_known, to_disposition_inputs

_REQUIRED_DISPOSITIONS = frozenset(
    {
        DispositionId("risk_tolerance"),
        DispositionId("time_discount"),
        DispositionId("ambiguity_aversion"),
        DispositionId("effort_tolerance"),
    }
)


def project_effective_weights(
    posterior: PreferencePosterior,
    trait_model: TraitModel,
    *,
    projection_version: str = PROJECTION_VERSION,
) -> EffectiveWeightVector:
    """Project `posterior` into the concrete `EffectiveWeightVector` M3 consumes.

    Pure and deterministic: same `posterior` + same `trait_model` + same
    `projection_version` always produce the same result. Never mutates
    `posterior` - every field read here is read, never written.

    Raises:
        PreferenceValidationError: `posterior.trait_schema_version` does not
            match `trait_model.version`; the posterior is missing a required
            core factor or disposition; or any `mu`/`sigma`/`alpha`/`beta`
            value the projection actually uses is not finite.
    """
    _validate_schema_compatibility(posterior, trait_model)
    _validate_covers_core_weights(posterior, trait_model)
    _validate_covers_dispositions(posterior)
    _validate_finite(posterior, trait_model)

    core_ids = trait_model.core_weight_factor_ids
    raw_weights = softmax_over_known(posterior.weights, core_ids)
    weights = WeightVector(weights=raw_weights)
    dispositions = to_disposition_inputs(posterior.dispositions)

    return EffectiveWeightVector(
        weights=weights,
        dispositions=dispositions,
        trait_schema_version=posterior.trait_schema_version,
        preference_engine_version=posterior.engine_version,
        projection_version=projection_version,
        read_transform=trait_model.read_transform,
        total_weight_evidence_count=sum(posterior.weight_evidence_count.values()),
        total_disposition_evidence_count=sum(posterior.disposition_evidence_count.values()),
    )


def _validate_schema_compatibility(posterior: PreferencePosterior, trait_model: TraitModel) -> None:
    if posterior.trait_schema_version != trait_model.version:
        msg = (
            f"posterior trait_schema_version={posterior.trait_schema_version} does not "
            f"match trait_model.version={trait_model.version}"
        )
        raise PreferenceValidationError(msg)


def _validate_covers_core_weights(posterior: PreferencePosterior, trait_model: TraitModel) -> None:
    missing = sorted(set(trait_model.core_weight_factor_ids) - set(posterior.weights))
    if missing:
        msg = f"posterior is missing a weight posterior for core factors: {missing}"
        raise PreferenceValidationError(msg)


def _validate_covers_dispositions(posterior: PreferencePosterior) -> None:
    missing = sorted(_REQUIRED_DISPOSITIONS - set(posterior.dispositions))
    if missing:
        msg = f"posterior is missing a disposition posterior for: {missing}"
        raise PreferenceValidationError(msg)


def _validate_finite(posterior: PreferencePosterior, trait_model: TraitModel) -> None:
    """The boundary where a non-finite posterior value actually gets caught.

    `WeightPosterior`/`DispositionPosterior` do not themselves reject NaN
    (`NaN <= 0` is `False`, so the domain types' own positivity validators let
    it through) - checked here on exactly the factors/dispositions this
    projection reads.
    """
    for factor_id in trait_model.core_weight_factor_ids:
        weight = posterior.weights[factor_id]
        if not math.isfinite(weight.mu) or not math.isfinite(weight.sigma):
            msg = f"weight posterior for {factor_id!r} has a non-finite mu/sigma"
            raise PreferenceValidationError(msg)
    for disposition_id in _REQUIRED_DISPOSITIONS:
        disposition = posterior.dispositions[disposition_id]
        if not math.isfinite(disposition.alpha) or not math.isfinite(disposition.beta):
            msg = f"disposition posterior for {disposition_id!r} has a non-finite alpha/beta"
            raise PreferenceValidationError(msg)
