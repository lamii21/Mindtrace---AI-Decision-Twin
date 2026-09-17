"""The confidence engine's versioned, validated constants (spec §06 §3).

Bundled the same way ``engines/mcda/config.py`` bundles the MCDA constants: one
frozen, versioned object rather than bare module constants, so "a configured
confidence model/version" is an explicit input a caller can name, inspect, and
- once real recalibration data exists (spec §06 §8) - swap out without
touching the engine's code at all.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

ENGINE_VERSION = "1"

_FrozenModel = ConfigDict(frozen=True, extra="forbid")
_WEIGHT_SUM_TOLERANCE = 1e-9


class RecalibrationParams(BaseModel):
    """The Platt-scaling pair `(alpha, beta)` from an offline logistic fit (spec §06 §8).

    Absent (`ConfidenceConfig.recalibration is None`) means exactly what spec
    §06 §8 says it means before `N_RECAL` resolved predictions exist: "confidence
    not yet calibrated" - never approximated by a default `(0, 1)` pair, which
    would silently claim a fit that was never performed.
    """

    model_config = _FrozenModel

    alpha: float
    beta: float


class ConfidenceConfig(BaseModel):
    """One named, versioned set of confidence constants. See spec §06 §3 for meanings."""

    model_config = _FrozenModel

    version: str = "1"
    a_evidence: float = 0.35
    b_ensemble: float = 0.20
    c_calibration: float = 0.20
    d_extraction: float = 0.10
    e_margin: float = 0.15
    k_eff: float = 4.0
    disagree_norm: float = 0.5
    label_disagree_penalty: float = 0.25
    degenerate_es_cutoff: float = 0.25
    degenerate_ensemble_cap: float = 0.50
    n_cal_min: int = 12
    hc_prior: float = 0.50
    n_recal: int = 30
    c_min: float = 0.35
    recalibration: RecalibrationParams | None = None

    @model_validator(mode="after")
    def _validate(self) -> ConfidenceConfig:
        if not self.version.strip():
            msg = "version must be non-empty"
            raise ValueError(msg)
        self._validate_weights()
        self._validate_constants()
        return self

    def _validate_weights(self) -> None:
        weights = {
            "a_evidence": self.a_evidence,
            "b_ensemble": self.b_ensemble,
            "c_calibration": self.c_calibration,
            "d_extraction": self.d_extraction,
            "e_margin": self.e_margin,
        }
        for name, value in weights.items():
            if not 0.0 <= value <= 1.0:
                msg = f"{name} must be in [0, 1], got {value}"
                raise ValueError(msg)
        total = sum(weights.values())
        if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
            msg = f"a..e weights must sum to 1.0, got {total}"
            raise ValueError(msg)

    def _validate_constants(self) -> None:
        if self.k_eff <= 0:
            msg = "k_eff must be > 0"
            raise ValueError(msg)
        if self.disagree_norm <= 0:
            msg = "disagree_norm must be > 0"
            raise ValueError(msg)
        unit_interval_fields = {
            "label_disagree_penalty": self.label_disagree_penalty,
            "degenerate_es_cutoff": self.degenerate_es_cutoff,
            "degenerate_ensemble_cap": self.degenerate_ensemble_cap,
            "hc_prior": self.hc_prior,
            "c_min": self.c_min,
        }
        for name, value in unit_interval_fields.items():
            if not 0.0 <= value <= 1.0:
                msg = f"{name} must be in [0, 1], got {value}"
                raise ValueError(msg)
        if self.n_cal_min < 1:
            msg = "n_cal_min must be >= 1"
            raise ValueError(msg)
        if self.n_recal < 1:
            msg = "n_recal must be >= 1"
            raise ValueError(msg)


DEFAULT_CONFIDENCE_CONFIG = ConfidenceConfig()
