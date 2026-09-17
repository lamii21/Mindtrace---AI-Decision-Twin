"""Value types the confidence engine (``mindtrace.engines.confidence``) consumes and produces.

Mirrors ``domain/decision.py``'s shape: frozen, validated-at-construction inputs
the engine receives explicitly, plus a self-contained, auditable result. Nothing
here is derived from an LLM (docs/spec/06-confidence-model.md §1: "narrated by
an LLM" is a *forbidden* source for `C`) and nothing here computes anything -
construction-time validation only enforces invariants the mathematics in
``docs/spec/06-confidence-model.md`` already assumes.

Three of the five confidence inputs (evidence posteriors, a real parallel-twin
ensemble, a resolved-prediction ledger) come from milestones that don't exist
yet (the Bayesian preference engine, ADR-007's ensemble, and the Prediction/
Outcome persistence layer respectively). Rather than fabricate them, every type
here that represents one of those signals is optional at the call site, and its
absence is carried through to :class:`ConfidenceInputs` as an explicit
"unavailable" marker - never silently treated as a favourable value.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mindtrace.domain.enums import DecisionOutcome
from mindtrace.domain.ids import FactorId

_FrozenModel = ConfigDict(frozen=True, extra="forbid")
_MIN_ENSEMBLE_SIZE = 2


class EnsembleObservation(BaseModel):
    """Scores and labels from a real parallel-twin ensemble (spec §06 §4.2, ADR-007).

    Requires at least 2 scores: a single (base-twin-only) score is not an
    ensemble and must not be passed here - the confidence engine treats "no
    `EnsembleObservation`" as the honest "ensemble unavailable" state instead.
    """

    model_config = _FrozenModel

    scores: tuple[float, ...]
    labels: tuple[DecisionOutcome, ...]

    @model_validator(mode="after")
    def _validate(self) -> EnsembleObservation:
        if len(self.scores) < _MIN_ENSEMBLE_SIZE:
            msg = (
                f"EnsembleObservation requires >= {_MIN_ENSEMBLE_SIZE} scores "
                f"(a real ensemble), got {len(self.scores)}"
            )
            raise ValueError(msg)
        if len(self.labels) != len(self.scores):
            msg = (
                f"labels must have the same length as scores: "
                f"{len(self.labels)} != {len(self.scores)}"
            )
            raise ValueError(msg)
        for score in self.scores:
            if not -1.0 <= score <= 1.0:
                msg = f"score out of [-1, 1]: {score}"
                raise ValueError(msg)
        return self


class CalibrationRecord(BaseModel):
    """One resolved `(predicted_confidence, was it correct)` pair (spec §06 §4.3)."""

    model_config = _FrozenModel

    predicted_confidence: float = Field(ge=0.0, le=1.0)
    correct: bool


class CalibrationLedger(BaseModel):
    """Resolved predictions available for `historical_calibration`, by domain scope.

    Both fields default to empty: until the Prediction/Outcome persistence layer
    exists, every caller passes ``None`` for the whole ledger, and
    `historical_calibration` takes the spec's own explicitly-defined small-`n`
    branch (term omitted, `calibrated=false`) - not a fabricated fallback.
    """

    model_config = _FrozenModel

    domain_records: tuple[CalibrationRecord, ...] = ()
    all_domain_records: tuple[CalibrationRecord, ...] = ()


class ExtractionSignal(BaseModel):
    """The factor-extraction instability signal (spec §06 §4.4).

    `single`: a caller asserting a real single extraction ran with a non-empty
    `rationale_span` for every known factor - the spec's own fixed default
    (`extraction_entropy = 0.10`) applies. `self_consistency`: a second
    extraction's per-factor agreement score against the first. There is no
    third "assume adequate without an extraction" path: `None` (no
    `ExtractionSignal` at all) is how a caller represents "no extraction
    pipeline exists yet", and the engine keeps that distinct from `single`.
    """

    model_config = _FrozenModel

    path: str  # "single" | "self_consistency"
    agreement: dict[FactorId, float] | None = None

    @model_validator(mode="after")
    def _validate(self) -> ExtractionSignal:
        if self.path not in {"single", "self_consistency"}:
            msg = f"path must be 'single' or 'self_consistency', got {self.path!r}"
            raise ValueError(msg)
        if self.path == "single" and self.agreement is not None:
            msg = "the 'single' path must not carry an agreement map"
            raise ValueError(msg)
        if self.path == "self_consistency":
            if not self.agreement:
                msg = "the 'self_consistency' path requires a non-empty agreement map"
                raise ValueError(msg)
            for factor_id, value in self.agreement.items():
                if not 0.0 <= value <= 1.0:
                    msg = f"agreement for {factor_id!r} out of [0, 1]: {value}"
                    raise ValueError(msg)
        return self

    @classmethod
    def single(cls) -> ExtractionSignal:
        """A real single extraction ran cleanly: use the spec's fixed default entropy."""
        return cls(path="single")

    @classmethod
    def self_consistency(cls, agreement: dict[FactorId, float]) -> ExtractionSignal:
        """A second extraction ran; `agreement[i]` is 1/0.5/0 per spec §06 §4.4."""
        return cls(path="self_consistency", agreement=dict(agreement))


class ConfidenceInputs(BaseModel):
    """The full audit trace behind one `C` (spec §06 §9's `ConfidenceInputs`).

    Every optional field being `None` means "this signal was unavailable when
    `C` was computed" - never "this signal was favourable". `calibrated` and
    `extraction_path` spell that state out explicitly rather than leaving a
    reader to infer it from a missing number.
    """

    model_config = _FrozenModel

    evidence_sufficiency: float = Field(ge=0.0, le=1.0)
    n_bar: float = Field(ge=0.0)
    coverage: float = Field(ge=0.0)
    ensemble_disagreement: float | None
    ensemble_term_capped: bool
    historical_calibration: float | None
    calibrated: str  # "true" | "false" | "cross_domain"
    calibration_n: int = Field(ge=0)
    extraction_entropy: float | None
    extraction_path: str  # "single" | "self_consistency" | "unavailable"
    margin_adequacy: float = Field(ge=0.0, le=1.0)
    margin: float


class ConfidenceResult(BaseModel):
    """The confidence engine's complete, self-contained answer (spec §06 §9).

    `credible_interval` is deliberately absent from this milestone: spec §06 §6
    defines it as seeded Monte Carlo over *trait posterior distributions*, and
    no such distributions exist yet (only point-estimate `WeightVector`/
    `DispositionInputs` - see M3). Sampling around a point estimate with an
    invented variance would be exactly the fabrication this engine exists to
    refuse, so the field is typed `None` until the preference engine that
    actually produces posteriors lands.
    """

    model_config = _FrozenModel

    confidence_engine_version: str
    confidence_config_version: str
    value: float = Field(ge=0.0, le=1.0)
    raw: float = Field(ge=0.0, le=1.0)
    calibrated_output: bool
    credible_interval: None
    inputs: ConfidenceInputs
    weights_used: dict[str, float]


__all__ = [
    "CalibrationLedger",
    "CalibrationRecord",
    "ConfidenceInputs",
    "ConfidenceResult",
    "EnsembleObservation",
    "ExtractionSignal",
]
