"""The MCDA engine's versioned, validated constants (spec §0).

Bundled into one frozen, versioned object rather than left as bare module
constants: a "configured decision model/version" is one of the engine's
explicit inputs, and this is the type that names it, carries its own
invariants, and gives ``docs/spec/05-mcda-mathematics.md`` §1d's status-quo
baseline (``baseline_n``) a single, clearly isolated home a later milestone
can evaluate or replace without touching the rest of the engine (M3's "preview
pattern" note).

``C_MIN`` (spec §0's model-confidence floor) is deliberately absent: it gates
on a quantity (``C``) this milestone does not compute. See
``mindtrace.domain.decision.DecisionResult`` for where that gate is *not*
applied and why.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

ENGINE_VERSION = "1"


class MCDAConfig(BaseModel):
    """One named, versioned set of MCDA constants. See spec §0 for every value's meaning."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = "1"
    tau_accept: float = 0.20
    tau_reject: float = -0.20
    coverage_min: float = 0.55
    ambiguity_coverage_slope: float = 0.15
    margin_ref: float = 0.10
    score_scale: float = 2.0
    baseline_n: float = 0.5
    k_risk: float = 1.7
    k_effort: float = 1.6
    time_discount_weight_slope: float = 0.6
    ambiguity_weight_bump: float = 0.4

    @model_validator(mode="after")
    def _validate(self) -> MCDAConfig:
        if not self.version.strip():
            msg = "version must be non-empty"
            raise ValueError(msg)
        if self.tau_accept <= 0:
            msg = "tau_accept must be > 0"
            raise ValueError(msg)
        if self.tau_reject != -self.tau_accept:
            msg = "tau_reject must equal -tau_accept (spec/05 s0: 'symmetric')"
            raise ValueError(msg)
        if not 0.0 <= self.coverage_min <= 1.0:
            msg = "coverage_min must be in [0, 1]"
            raise ValueError(msg)
        if not 0.0 <= self.ambiguity_coverage_slope <= 1.0:
            msg = "ambiguity_coverage_slope must be in [0, 1]"
            raise ValueError(msg)
        if self.margin_ref <= 0:
            msg = "margin_ref must be > 0"
            raise ValueError(msg)
        if self.score_scale <= 0:
            msg = "score_scale must be > 0"
            raise ValueError(msg)
        if not 0.0 <= self.baseline_n <= 1.0:
            msg = "baseline_n must be in [0, 1]"
            raise ValueError(msg)
        if self.k_risk <= 0 or self.k_effort <= 0:
            msg = "k_risk and k_effort must be > 0"
            raise ValueError(msg)
        return self


DEFAULT_MCDA_CONFIG = MCDAConfig()
