"""`margin_adequacy` (spec §06 §4.5).

`margin` itself (`m = |S| - TAU_ACCEPT`) is already computed by M3's MCDA
engine and carried on `DecisionResult.margin` - this module does not
recompute it, only maps it through the confidence-specific `margin_ref` scale.
For an UNCERTAIN-by-band decision `m < 0`, clamping alone (not a branch) gives
`margin_adequacy = 0`, matching spec exactly.
"""

from __future__ import annotations

from mindtrace.engines.confidence._numeric import clamp
from mindtrace.engines.mcda.config import MCDAConfig


def margin_adequacy(margin: float, mcda_config: MCDAConfig) -> float:
    """`clamp(margin / MARGIN_REF, 0, 1)` (spec §06 §4.5)."""
    return clamp(margin / mcda_config.margin_ref, 0.0, 1.0)
