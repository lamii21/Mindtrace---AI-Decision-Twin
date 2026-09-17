"""The Bayesian preference engine: deterministic posterior estimation over trait priors.

Pure, composable, versioned - see ``docs/adr/ADR-005-bayesian-preference-estimation.md``
and ``docs/spec/04-trait-model.md``. Produces preference *state* (posteriors),
never a decision - ``mindtrace.engines.mcda`` and
``mindtrace.engines.confidence`` are the engines that read this state.
"""

from __future__ import annotations

from mindtrace.engines.preference.config import (
    DEFAULT_PREFERENCE_CONFIG,
    ENGINE_VERSION,
    PreferenceConfig,
)
from mindtrace.engines.preference.errors import PreferenceValidationError
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
from mindtrace.engines.preference.prior import initial_posterior
from mindtrace.engines.preference.update import (
    apply_disposition_observations,
    apply_pairwise_observations,
    laplace_map_update,
    update_disposition,
    update_dispositions,
    update_weights,
)

__all__ = [
    "DEFAULT_PREFERENCE_CONFIG",
    "ENGINE_VERSION",
    "PreferenceConfig",
    "PreferenceValidationError",
    "apply_disposition_observations",
    "apply_pairwise_observations",
    "disposition_confidence",
    "disposition_credible_interval",
    "disposition_report",
    "disposition_value",
    "effective_sample_sizes",
    "initial_posterior",
    "laplace_map_update",
    "softmax_over_known",
    "to_disposition_inputs",
    "update_disposition",
    "update_dispositions",
    "update_weights",
    "weight_confidence",
    "weight_credible_interval",
    "weight_report",
]
