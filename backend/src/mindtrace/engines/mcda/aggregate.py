"""Aggregate value, decision score, and per-factor contributions (spec §3, §4, §6).

As in ``normalize.py``: every summation walks an explicitly sorted sequence of
factor ids, never a bare set/dict iteration, so results are byte-identical
regardless of hash randomisation (spec §10 property 7).
"""

from __future__ import annotations

from collections.abc import Mapping

from mindtrace.domain.ids import FactorId
from mindtrace.engines.mcda.config import MCDAConfig


def aggregate_value(
    weights: Mapping[FactorId, float], normalized: Mapping[FactorId, float]
) -> float:
    """`V(o) = sum_i w_i * n_i(o)` (spec §3). `weights`/`normalized` share the known set."""
    return sum(weights[factor_id] * normalized[factor_id] for factor_id in sorted(weights))


def decision_score(v_a: float, v_b: float, config: MCDAConfig) -> tuple[float, float]:
    """`(raw_score, score)` - the pre-clamp value and the clamped `S` (spec §4).

    `raw_score` is what :func:`factor_contributions` sums to exactly; `score`
    is what spec §5's decision rule and §7's margin are computed from. They
    differ only when clamping actually triggers (see
    :class:`~mindtrace.domain.decision.DecisionResult`'s docstring).
    """
    raw_score = config.score_scale * (v_a - v_b)
    score = max(-1.0, min(1.0, raw_score))
    return raw_score, score


def factor_contributions(
    weights: Mapping[FactorId, float],
    normalized_a: Mapping[FactorId, float],
    normalized_b: Mapping[FactorId, float],
    config: MCDAConfig,
) -> dict[FactorId, float]:
    """`c_i = SCORE_SCALE * w_i * (n_i(A) - n_i(B))` for every factor in `weights` (spec §6).

    Computed on the **unclamped** basis: `sum(factor_contributions(...).values())`
    equals `raw_score` from :func:`decision_score`, not the clamped `score`
    (spec §6: "Identity (pre-clamp)").
    """
    return {
        factor_id: config.score_scale
        * weights[factor_id]
        * (normalized_a[factor_id] - normalized_b[factor_id])
        for factor_id in sorted(weights)
    }


def contribution_percentages(contributions: Mapping[FactorId, float]) -> dict[FactorId, float]:
    """`c_i% = 100 * c_i / sum_j |c_j|` (spec §6). All zero if every contribution is zero."""
    total_abs = sum(abs(contributions[factor_id]) for factor_id in sorted(contributions))
    if total_abs <= 0:
        return dict.fromkeys(contributions, 0.0)
    return {factor_id: 100.0 * value / total_abs for factor_id, value in contributions.items()}
