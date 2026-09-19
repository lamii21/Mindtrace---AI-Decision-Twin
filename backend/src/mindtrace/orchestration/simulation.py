"""The in-memory decision simulation pipeline (M6-B).

Composes M5 extraction, M6-A projection, M3 MCDA, and M4 confidence - and
computes nothing itself.

```
scenario -> M5 extract_factors[_self_consistency] -> ExtractionOutcome
posterior -> M6-A project_effective_weights -> EffectiveWeightVector
(ExtractionOutcome.factors, EffectiveWeightVector) -> M3 decide -> DecisionResult
(DecisionResult, n_eff, extraction signal) -> M4 compute_confidence -> ConfidenceResult
```

Every one of those four calls is a real call into the engine that already
owns that mathematics (`extract_factors`/`extract_factors_self_consistency`,
`project_effective_weights`, `decide`, `compute_confidence`) - nothing here
recomputes a score, a weight, a posterior, or a confidence value. `S`
(`decision.score`), `C` (`confidence.value`), and extraction uncertainty
(`extraction.agreement`/the `ExtractionSignal` built from it) are three
independent fields on `SimulationResult`, never combined into one another.
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, model_validator

from mindtrace.domain.confidence import ConfidenceResult, ExtractionSignal
from mindtrace.domain.decision import DecisionResult
from mindtrace.domain.enums import ExtractionMode
from mindtrace.domain.factors import FactorTaxonomy
from mindtrace.domain.traits import EffectiveWeightVector, PreferencePosterior, TraitModel
from mindtrace.engines.confidence.compute import compute_confidence
from mindtrace.engines.confidence.config import DEFAULT_CONFIDENCE_CONFIG, ConfidenceConfig
from mindtrace.engines.mcda.config import DEFAULT_MCDA_CONFIG, MCDAConfig
from mindtrace.engines.mcda.decide import decide
from mindtrace.engines.preference.config import PROJECTION_VERSION
from mindtrace.engines.preference.posterior import effective_sample_sizes
from mindtrace.engines.preference.projection import project_effective_weights
from mindtrace.llm.client import LLMClient
from mindtrace.llm.config import ExtractionConfig
from mindtrace.llm.extraction import extract_factors, extract_factors_self_consistency
from mindtrace.llm.schema import ExtractionOutcome
from mindtrace.orchestration.errors import SimulationError

SIMULATION_VERSION = "1"

_FrozenModel = ConfigDict(frozen=True, extra="forbid")


class SimulationConfig(BaseModel):
    """The versioned "how to run" knobs for one `simulate()` call.

    No trait/factor/prior data lives here - only which sub-engine
    configuration and mode to use. `extraction_config` has no default
    (`ExtractionConfig` itself requires `provider`/`model` explicitly, M5's
    own decision); every other field falls back to its owning engine's
    already-versioned default.
    """

    model_config = _FrozenModel

    extraction_config: ExtractionConfig
    mcda_config: MCDAConfig = DEFAULT_MCDA_CONFIG
    confidence_config: ConfidenceConfig = DEFAULT_CONFIDENCE_CONFIG
    projection_version: str = PROJECTION_VERSION
    self_consistency: bool = False


class SimulationResult(BaseModel):
    """One complete, auditable simulation.

    A thin composition of the four engines' own result types, never a
    re-derivation of their fields. Every question M6-B §3 asks is answered
    by reading one sub-result
    directly: extracted/unknown factors and their provenance ->
    `extraction`; effective weights/dispositions and their provenance ->
    `preference`; `S`/label/coverage/margin/contributions -> `decision`;
    `C` and why it is what it is -> `confidence`. `scenario_content_hash` is
    a one-way fingerprint of the scenario text, not the text itself - the
    result never retains the raw scenario (M6-B §15).
    """

    model_config = _FrozenModel

    simulation_version: str
    scenario_content_hash: str
    extraction: ExtractionOutcome
    preference: EffectiveWeightVector
    decision: DecisionResult
    confidence: ConfidenceResult

    @model_validator(mode="after")
    def _score_and_confidence_are_independent_fields(self) -> SimulationResult:
        # A structural guard, not a mathematical one: `decision`/`confidence`
        # are two separately-typed sub-objects on this model - there is no
        # field here (and never will be) computed as some function of both,
        # e.g. `score * confidence`. This validator exists only so that
        # invariant is asserted somewhere executable, not just documented.
        assert isinstance(self.decision, DecisionResult)
        assert isinstance(self.confidence, ConfidenceResult)
        return self


def simulate(
    scenario_text: str,
    taxonomy: FactorTaxonomy,
    trait_model: TraitModel,
    posterior: PreferencePosterior,
    llm_client: LLMClient,
    *,
    config: SimulationConfig,
) -> SimulationResult:
    """Run one complete decision simulation, end to end, in memory.

    Raises:
        SimulationError: `taxonomy.version` does not match
            `trait_model.factor_schema_version`.
        mindtrace.engines.preference.errors.PreferenceValidationError:
            `posterior` is incompatible with `trait_model` (M6-A's own
            contract - propagated unchanged, not re-wrapped).
        mindtrace.engines.mcda.errors.MCDAValidationError: the projected
            weights are incompatible with `taxonomy` (M3's own contract -
            propagated unchanged, not re-wrapped).

    An LLM extraction failure never raises: M5's `extract_factors` always
    returns a valid `ExtractionOutcome`, `failed` or not, and this function
    passes its `factors` (every core factor `known=False` on failure)
    straight into `decide()` exactly as-is - M3's own coverage gate is what
    turns that into `UNCERTAIN`, not a check written here.
    """
    _validate_schema_compatibility(taxonomy, trait_model)

    if config.self_consistency:
        extraction = extract_factors_self_consistency(
            scenario_text, taxonomy, llm_client, config=config.extraction_config
        )
    else:
        extraction = extract_factors(
            scenario_text, taxonomy, llm_client, config=config.extraction_config
        )

    preference = project_effective_weights(
        posterior, trait_model, projection_version=config.projection_version
    )

    decision = decide(
        taxonomy,
        preference.weights,
        extraction.factors,
        preference.dispositions,
        config=config.mcda_config,
    )

    n_eff = effective_sample_sizes(posterior.weights, trait_model)
    extraction_signal = _extraction_signal_for(extraction)
    confidence = compute_confidence(
        decision,
        n_eff=n_eff,
        ensemble=None,
        calibration=None,
        extraction=extraction_signal,
        config=config.confidence_config,
        mcda_config=config.mcda_config,
    )

    return SimulationResult(
        simulation_version=SIMULATION_VERSION,
        scenario_content_hash=_hash_scenario(scenario_text),
        extraction=extraction,
        preference=preference,
        decision=decision,
        confidence=confidence,
    )


def _validate_schema_compatibility(taxonomy: FactorTaxonomy, trait_model: TraitModel) -> None:
    if taxonomy.version != trait_model.factor_schema_version:
        msg = (
            f"taxonomy.version={taxonomy.version} does not match "
            f"trait_model.factor_schema_version={trait_model.factor_schema_version}"
        )
        raise SimulationError(msg)


def _extraction_signal_for(outcome: ExtractionOutcome) -> ExtractionSignal | None:
    """Map M5's `ExtractionOutcome` state onto the `ExtractionSignal` M4 already accepts.

    A lookup, not a computation. A failed extraction has no signal
    at all (`None`, genuinely unavailable); a successful self-consistency
    pass hands M4 exactly the `agreement` M5 already computed; a successful
    single pass asserts `ExtractionSignal.single()`, which M5's own schema
    already guarantees the precondition for (`known=true` requires a
    non-empty `rationale_span` on every factor, spec/06 §4.4's own
    definition of that fast path).
    """
    if outcome.status == "failed":
        return None
    if outcome.metadata.mode is ExtractionMode.SELF_CONSISTENCY:
        assert outcome.agreement is not None  # guaranteed by extract_factors_self_consistency
        return ExtractionSignal.self_consistency(outcome.agreement)
    return ExtractionSignal.single()


def _hash_scenario(scenario_text: str) -> str:
    """A deterministic, one-way fingerprint - never the scenario text itself.

    M6-B §15: the scenario is user-controlled data, not retained here.
    """
    return hashlib.sha256(scenario_text.encode("utf-8")).hexdigest()
