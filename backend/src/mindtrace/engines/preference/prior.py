"""The prior *as* the zero-evidence posterior (ADR-005, spec/04 §3): straight from `traits.yaml`.

No trait value is hard-coded here. ``initial_posterior`` only reshapes the
already-loaded, already-validated ``TraitModel`` (M1) into the engine's
``PreferencePosterior`` state, with every evidence count at zero - "which
prior was used to derive this posterior?" is answered by
`trait_schema_version` alone.
"""

from __future__ import annotations

from mindtrace.domain.traits import (
    DispositionPosterior,
    PreferencePosterior,
    TraitModel,
    WeightPosterior,
)
from mindtrace.engines.preference.config import ENGINE_VERSION


def initial_posterior(
    trait_model: TraitModel, *, engine_version: str = ENGINE_VERSION
) -> PreferencePosterior:
    """A `PreferencePosterior` with every trait at its `traits.yaml` prior and zero evidence."""
    weights = {
        w.factor: WeightPosterior(factor=w.factor, mu=w.prior.mu, sigma=w.prior.sigma)
        for w in trait_model.weights
    }
    dispositions = {
        d.id: DispositionPosterior(id=d.id, alpha=d.prior.alpha, beta=d.prior.beta)
        for d in trait_model.dispositions
    }
    return PreferencePosterior(
        engine_version=engine_version,
        trait_schema_version=trait_model.version,
        weights=weights,
        dispositions=dispositions,
        weight_evidence_count=dict.fromkeys(weights, 0),
        disposition_evidence_count=dict.fromkeys(dispositions, 0),
    )
