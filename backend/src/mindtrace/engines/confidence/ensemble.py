"""`ensemble_disagreement` and its degenerate-twin guard (spec §06 §4.2).

This module's own math is unchanged since before M10 - ADR-007 did not
modify it, only gave it a real caller: `services.decision_service.
run_simulation` now builds a real `EnsembleObservation` from
`engines.simulation.parallel.run_twin_ensemble`'s per-twin scores/labels and
passes it in, where every caller before M10 always passed `None`.
`orchestration.simulate()`'s own internal confidence call still passes
`ensemble=None` (that result is computed but not the one `run_simulation`
persists - see `services.decision_service.run_simulation`'s docstring) - so
both states handled below are genuinely live, not one historical and one
current.

`ensemble` is `None` whenever no parallel-twin ensemble was computed for
this call - the honest "ensemble unavailable" state, carried straight
through as `(None, None, False)` rather than synthesised from a single
base-twin score (never `(1.0 - 0.0, 0.0, False)` or any other fabricated
stand-in). When `ensemble` is a real `EnsembleObservation` (>= 2 scores),
`ensemble_term` returns a genuine dispersion-plus-label-disagreement measure
instead, computed only from `ensemble.scores`/`ensemble.labels` - this
module never sees a `DecisionResult` or its `score` directly; the
translation from each twin's own `decision.score` into `ensemble.scores` is
`engines.simulation.parallel.ensemble_observation_from`'s job, not this
module's. That separation is what keeps the resulting confidence term a
measure of disagreement *between* twins, never a restatement of any one
twin's own decision score.
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
