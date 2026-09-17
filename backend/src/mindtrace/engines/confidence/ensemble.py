"""`ensemble_disagreement` and its degenerate-twin guard (spec §06 §4.2).

`EnsembleObservation` is `None` whenever no real parallel-twin ensemble exists
yet (ADR-007 is unimplemented as of this milestone) - that is the "ensemble
unavailable" state, carried straight through as `(None, None, False)` rather
than synthesised from a single base-twin score.
"""

from __future__ import annotations

import statistics

from mindtrace.domain.confidence import EnsembleObservation
from mindtrace.engines.confidence._numeric import clamp
from mindtrace.engines.confidence.config import ConfidenceConfig


def ensemble_term(
    ensemble: EnsembleObservation | None,
    evidence_sufficiency_value: float,
    config: ConfidenceConfig,
) -> tuple[float | None, float | None, bool]:
    """`(term fed into the combination, ensemble_disagreement, capped?)`.

    `term` is `(1 - ensemble_disagreement)`, already passed through the
    degenerate-twin guard (spec §06 §4.2): when `evidence_sufficiency` is
    below `degenerate_es_cutoff`, a near-flat twin's fake agreement cannot
    push `term` above `degenerate_ensemble_cap`.
    """
    if ensemble is None:
        return None, None, False

    dispersion = clamp(statistics.pstdev(ensemble.scores) / config.disagree_norm, 0.0, 1.0)
    unanimous = len(set(ensemble.labels)) == 1
    penalty = 0.0 if unanimous else config.label_disagree_penalty
    disagreement = clamp(dispersion + penalty, 0.0, 1.0)

    term = 1.0 - disagreement
    capped = False
    degenerate = evidence_sufficiency_value < config.degenerate_es_cutoff
    if degenerate and term > config.degenerate_ensemble_cap:
        term = config.degenerate_ensemble_cap
        capped = True

    return term, disagreement, capped
