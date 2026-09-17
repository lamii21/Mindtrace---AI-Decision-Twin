"""`evidence_sufficiency` (spec §06 §4.1).

`N_eff_i` - the effective sample size behind factor `i`'s weight posterior - is
defined in spec §04 as a function of prior/posterior variance from the (not yet
built) Bayesian preference engine. Rather than invent that engine here, this
function takes `n_eff` as an explicit, optional per-factor input: `None`
(or a factor missing from the map) means "no posterior update has ever touched
this weight", which is mathematically `N_eff_i = 0` - the honest value the
spec's own formula produces when `sigma_post == sigma_prior`, not a fabricated
stand-in. `evidence_sufficiency` is therefore always computable, never
"unavailable"; it simply saturates at its floor until real posterior data
exists.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from mindtrace.domain.ids import FactorId
from mindtrace.engines.confidence.config import ConfidenceConfig


def evidence_sufficiency(
    n_eff: Mapping[FactorId, float] | None,
    known_weights: Mapping[FactorId, float],
    coverage: float,
    config: ConfidenceConfig,
) -> tuple[float, float]:
    """`(evidence_sufficiency, n_bar)` (spec §06 §4.1).

    `known_weights` are the decision's renormalised known-factor weights
    (`Contribution.weight` from `DecisionResult`, spec §05 §2c) - the same
    `w_i` the formula's decision-weighted mean is defined over.
    """
    if n_eff is None:
        n_bar = 0.0
    else:
        n_bar = sum(known_weights[fid] * n_eff.get(fid, 0.0) for fid in sorted(known_weights))
    saturation = 1.0 - math.exp(-n_bar / config.k_eff)
    return coverage**0.5 * saturation, n_bar
