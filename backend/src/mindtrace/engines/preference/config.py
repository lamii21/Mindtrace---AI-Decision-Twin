"""The preference engine's versioned, validated update-algorithm hyperparameters.

Trait *priors* (`mu`/`sigma` per weight, `alpha`/`beta` per disposition) are
never duplicated here - they live in ``schema/traits.yaml``, loaded through
``mindtrace.domain.traits.TraitModel`` (M1). This module holds only the
update algorithm's own constants (ADR-005, spec/04 §3, spec/07 §4): the fixed
Newton iteration count, damping, the posterior `sigma` floor, and the two
update strengths (`s`, `kappa`) those specs name explicitly.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

ENGINE_VERSION = "1"
# The posterior -> MCDA-weight-snapshot transformation (`projection.py`, M6-A) is
# versioned separately from ENGINE_VERSION: a future change to how a
# posterior is read into an EffectiveWeightVector (e.g. a different
# normalization) need not imply the Laplace/Beta update math itself changed,
# and vice versa. Bump this whenever `project_effective_weights`'s own
# transformation changes.
PROJECTION_VERSION = "1"

_FrozenModel = ConfigDict(frozen=True, extra="forbid")


class PreferenceConfig(BaseModel):
    """One named, versioned set of preference-update constants.

    `newton_damping` and `sigma_floor` are engineering choices spec/04 §3/§7
    require to exist ("fixed damping", "a sigma floor") but does not pin to a
    specific number - documented in the M4 final report's Deviations section,
    not silently invented.
    """

    model_config = _FrozenModel

    version: str = "1"
    newton_steps: int = 25  # spec/04 §3: "N Newton steps (fixed N = 25...)"
    newton_damping: float = 1.0  # undamped: the objective is jointly concave (log-sigmoid
    # likelihood + Gaussian log-prior), so a full Newton step is a valid ascent at every
    # iteration; 25 fixed steps is ample headroom even for well-separated observations.
    sigma_floor: float = 0.05  # guards against over-confident collapse (spec/04 §7); chosen
    # well below traits.yaml's prior sigmas (1.4-1.5) so it only ever binds after
    # substantial evidence, never in sparse/cold-start regimes.
    pseudocount_kappa: float = 1.5  # spec/04 §3, spec/07 §4.2; schema/interview.yaml's own value
    logistic_scale_s: float = 0.6  # spec/04 §3; schema/interview.yaml's own value

    @model_validator(mode="after")
    def _validate(self) -> PreferenceConfig:
        if not self.version.strip():
            msg = "version must be non-empty"
            raise ValueError(msg)
        if self.newton_steps < 1:
            msg = "newton_steps must be >= 1"
            raise ValueError(msg)
        if self.newton_damping <= 0:
            msg = "newton_damping must be > 0"
            raise ValueError(msg)
        if self.sigma_floor <= 0:
            msg = "sigma_floor must be > 0"
            raise ValueError(msg)
        if self.pseudocount_kappa <= 0:
            msg = "pseudocount_kappa must be > 0"
            raise ValueError(msg)
        if self.logistic_scale_s <= 0:
            msg = "logistic_scale_s must be > 0"
            raise ValueError(msg)
        return self


DEFAULT_PREFERENCE_CONFIG = PreferenceConfig()
