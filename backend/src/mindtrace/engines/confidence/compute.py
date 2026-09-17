"""The confidence engine's public entry point: `compute_confidence`.

Pure composition over ``evidence.py``/``ensemble.py``/``calibration.py``/
``extraction.py``/``margin.py``/``aggregate.py``: no I/O, no clock, no
randomness, no LLM. Takes a `DecisionResult` from `mindtrace.engines.mcda` as
a **read-only** input - this module never recomputes `S`, `coverage`, or
`margin`, and never writes back into the `DecisionResult` it was given.

This module does not wire `C` into a final `ACCEPT`/`REJECT`/`UNCERTAIN`
label. `is_low_confidence`/`confidence_uncertain_reason` below are the
composable primitive a later milestone's `/simulate` orchestration (roadmap
M7) uses to do that; M3's `decide()` and its coverage/score-band gates are
untouched by this module, and its own deferred confidence gate is not
duplicated here.
"""

from __future__ import annotations

from collections.abc import Mapping

from mindtrace.domain.confidence import (
    CalibrationLedger,
    ConfidenceInputs,
    ConfidenceResult,
    EnsembleObservation,
    ExtractionSignal,
)
from mindtrace.domain.decision import DecisionResult
from mindtrace.domain.enums import UncertainReason
from mindtrace.domain.ids import FactorId
from mindtrace.engines.confidence._numeric import stable_sigmoid
from mindtrace.engines.confidence.aggregate import combine_terms
from mindtrace.engines.confidence.calibration import historical_calibration
from mindtrace.engines.confidence.config import (
    DEFAULT_CONFIDENCE_CONFIG,
    ENGINE_VERSION,
    ConfidenceConfig,
)
from mindtrace.engines.confidence.ensemble import ensemble_term as _ensemble_term
from mindtrace.engines.confidence.evidence import evidence_sufficiency as _evidence_sufficiency
from mindtrace.engines.confidence.extraction import extraction_entropy as _extraction_entropy
from mindtrace.engines.confidence.margin import margin_adequacy as _margin_adequacy
from mindtrace.engines.mcda.config import DEFAULT_MCDA_CONFIG, MCDAConfig


def compute_confidence(
    decision: DecisionResult,
    *,
    n_eff: Mapping[FactorId, float] | None = None,
    ensemble: EnsembleObservation | None = None,
    calibration: CalibrationLedger | None = None,
    extraction: ExtractionSignal | None = None,
    config: ConfidenceConfig = DEFAULT_CONFIDENCE_CONFIG,
    mcda_config: MCDAConfig = DEFAULT_MCDA_CONFIG,
) -> ConfidenceResult:
    """Compute `C` for `decision`. Every optional signal defaults to "unavailable", not favourable.

    Raises:
        ConfidenceValidationError: if `extraction` is a `self_consistency`
            signal whose agreement map does not cover exactly `decision`'s
            known-factor set.
    """
    known_weights = {c.factor_id: c.weight for c in decision.contributions}

    es, n_bar = _evidence_sufficiency(n_eff, known_weights, decision.coverage, config)
    ens_term, ens_disagreement, ens_capped = _ensemble_term(ensemble, es, config)
    hc, calibrated_status, calibration_n = historical_calibration(calibration, config)
    entropy, extraction_path = _extraction_entropy(extraction, known_weights)
    extraction_term = None if entropy is None else 1.0 - entropy
    m_adequacy = _margin_adequacy(decision.margin, mcda_config)

    raw_c, weights_used = combine_terms(
        evidence_sufficiency=es,
        ensemble_term=ens_term,
        historical_calibration=hc,
        extraction_term=extraction_term,
        margin_adequacy=m_adequacy,
        config=config,
    )

    if config.recalibration is not None:
        value = stable_sigmoid(config.recalibration.alpha + config.recalibration.beta * raw_c)
        calibrated_output = True
    else:
        value = raw_c
        calibrated_output = False

    inputs = ConfidenceInputs(
        evidence_sufficiency=es,
        n_bar=n_bar,
        coverage=decision.coverage,
        ensemble_disagreement=ens_disagreement,
        ensemble_term_capped=ens_capped,
        historical_calibration=hc,
        calibrated=calibrated_status,
        calibration_n=calibration_n,
        extraction_entropy=entropy,
        extraction_path=extraction_path,
        margin_adequacy=m_adequacy,
        margin=decision.margin,
    )

    return ConfidenceResult(
        confidence_engine_version=ENGINE_VERSION,
        confidence_config_version=config.version,
        value=value,
        raw=raw_c,
        calibrated_output=calibrated_output,
        credible_interval=None,
        inputs=inputs,
        weights_used=weights_used,
    )


def is_low_confidence(confidence: ConfidenceResult, config: ConfidenceConfig) -> bool:
    """`C < C_MIN` (spec §06 §7's restated label gate) - a pure predicate, no label side effects."""
    return confidence.value < config.c_min


def confidence_uncertain_reason(
    confidence: ConfidenceResult, config: ConfidenceConfig
) -> UncertainReason | None:
    """`low_model_confidence` if the gate fires, else `None` - not wired into `decide()`."""
    if is_low_confidence(confidence, config):
        return UncertainReason.LOW_MODEL_CONFIDENCE
    return None
