"""Ensemble disagreement diagnostics the confidence engine has no slot for (M10; ADR-007).

Dispersion of the twins' scores already feeds ``ConfidenceResult.inputs.
ensemble_disagreement`` via ``engines.confidence.ensemble.ensemble_term`` -
never recomputed here. This module only adds the two diagnostics ADR-007
names that M4 does not: ``label_consensus`` (unanimous/majority/split) and
``conflict_axis`` (the factor whose per-twin contribution varies the most).
"""

from __future__ import annotations

import statistics
from collections import Counter
from collections.abc import Sequence
from typing import Literal

from mindtrace.domain.enums import DecisionOutcome
from mindtrace.domain.ids import FactorId
from mindtrace.domain.simulation import TwinConfigResult

_MIN_TWINS_FOR_CONFLICT_AXIS = 2


def label_consensus(
    labels: Sequence[DecisionOutcome],
) -> Literal["unanimous", "majority", "split"]:
    """Classify agreement across the twins' own raw labels.

    Unweighted - see ``synthesis.py`` for the base-twin-counts-double *vote*,
    a separate, weighted computation.

    Raises:
        ValueError: ``labels`` is empty.
    """
    if not labels:
        msg = "label_consensus requires at least one label"
        raise ValueError(msg)
    counts = Counter(labels)
    if len(counts) == 1:
        return "unanimous"
    _winner, winner_count = counts.most_common(1)[0]
    if winner_count > len(labels) / 2:
        return "majority"
    return "split"


def conflict_axis(twin_results: Sequence[TwinConfigResult]) -> tuple[FactorId, ...]:
    """The factor(s) whose per-twin ``raw_contribution`` has the highest variance (ADR-007).

    ``docs/api/08`` s5 types this as a *list* - more than one factor can tie
    for maximum variance, and every tied factor is reported, not an
    arbitrarily chosen one. Deterministic: the returned tuple is sorted by
    ``FactorId``. Empty if fewer than 2 twins, or no factor appears in any
    twin's contributions at all.
    """
    if len(twin_results) < _MIN_TWINS_FOR_CONFLICT_AXIS:
        return ()

    per_factor: dict[FactorId, list[float]] = {}
    for result in twin_results:
        for contribution in result.decision.contributions:
            per_factor.setdefault(contribution.factor_id, []).append(contribution.raw_contribution)
    if not per_factor:
        return ()

    variances = {
        factor_id: (statistics.pvariance(values) if len(values) > 1 else 0.0)
        for factor_id, values in per_factor.items()
    }
    max_variance = max(variances.values())
    return tuple(sorted(factor_id for factor_id, v in variances.items() if v == max_variance))


__all__ = ["conflict_axis", "label_consensus"]
