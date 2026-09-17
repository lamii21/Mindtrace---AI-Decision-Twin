"""Factor normalisation and weight adjustment (spec §1, §2).

Every function here is pure and takes its config/disposition inputs
explicitly - no reading a global, no re-deriving anything from a twin. All
summation is over an explicitly **sorted** sequence of factor ids, never a
bare ``set``/``frozenset`` iteration: Python's hash-randomised set order would
otherwise make floating-point summation order (and so, in principle, the
last-bit result) vary between interpreter runs, which would break spec §10
property 7 (byte-identical results across runs/processes).
"""

from __future__ import annotations

from collections.abc import Mapping

from mindtrace.domain.decision import DispositionInputs
from mindtrace.domain.enums import FactorDirection
from mindtrace.domain.factors import FactorSpec
from mindtrace.domain.ids import FactorId
from mindtrace.engines.mcda.config import MCDAConfig

_RISK_CURVE_FACTORS = frozenset({FactorId("downside_risk"), FactorId("financial_security")})
_EFFORT_CURVE_FACTOR = FactorId("time_demand")
_TIME_DISCOUNT_FACTORS = frozenset({FactorId("option_value"), FactorId("long_term_value")})
_AMBIGUITY_BUMP_FACTOR = FactorId("reversibility")


def curve_exponent(
    factor_id: FactorId, dispositions: DispositionInputs, config: MCDAConfig
) -> float:
    """The disposition-shaped exponent `gamma` for `factor_id` (spec §1b table).

    Neutral dispositions (all 0.5) always give `gamma = 1` for every factor -
    spec §10 property 8.
    """
    # float(...): float.__pow__'s typeshed signature can return a non-float type (a negative
    # base raised to a fractional power is complex in general), so mypy sees `Any` here even
    # though every value MCDAConfig/DispositionInputs can hold keeps this call real-valued.
    if factor_id in _RISK_CURVE_FACTORS:
        return float(config.k_risk ** (2 * dispositions.risk_tolerance - 1))
    if factor_id == _EFFORT_CURVE_FACTOR:
        return float(config.k_effort ** (2 * dispositions.effort_tolerance - 1))
    return 1.0


def normalize_factor(
    spec: FactorSpec,
    a: float,
    dispositions: DispositionInputs,
    config: MCDAConfig,
) -> float:
    """`n_i(o)` for one factor: anchor -> curve-shaped `s` -> polarity-corrected `n` (spec §1a-c).

    `a` is the raw `[0, 1]` anchor (``spec.anchor_for(level)``), passed in
    rather than a `ScaleLevel` so this function stays agnostic to *how* the
    caller arrived at the anchor (a known level, or - for the status-quo
    baseline - `config.baseline_n` standing in for one).
    """
    gamma = curve_exponent(spec.id, dispositions, config)
    shaped = float(a**gamma)
    if spec.direction is FactorDirection.BENEFIT:
        return shaped
    return 1.0 - shaped


def adjust_weights(
    raw: Mapping[FactorId, float],
    dispositions: DispositionInputs,
    config: MCDAConfig,
) -> dict[FactorId, float]:
    """`w_i^adj` over every factor in `raw` (spec §2b)."""
    adjusted = dict(raw)
    time_discount_multiplier = 1.0 - config.time_discount_weight_slope * dispositions.time_discount
    for factor_id in sorted(_TIME_DISCOUNT_FACTORS & adjusted.keys()):
        adjusted[factor_id] *= time_discount_multiplier
    if _AMBIGUITY_BUMP_FACTOR in adjusted:
        bump = 1.0 + config.ambiguity_weight_bump * dispositions.ambiguity_aversion
        adjusted[_AMBIGUITY_BUMP_FACTOR] *= bump
    return adjusted


def renormalize_known(
    adjusted: Mapping[FactorId, float],
    known: tuple[FactorId, ...],
) -> tuple[dict[FactorId, float], float]:
    """`w_i` for `i in known` plus `coverage` (spec §2c).

    `known` must already be duplicate-free and is iterated in the order
    given - callers pass a pre-sorted tuple (`FactorVector.known_ids()`) so
    summation order is deterministic regardless of dict/hash-set ordering.
    Never divides by zero: an empty `known`, or a `known` subset whose
    adjusted weights happen to sum to <= 0, yields `coverage = 0.0` and every
    `w_i = 0.0` rather than raising (spec §10 property 9).
    """
    total_adjusted = sum(adjusted[factor_id] for factor_id in sorted(adjusted))
    known_sum = sum(adjusted[factor_id] for factor_id in known)

    coverage = known_sum / total_adjusted if total_adjusted > 0 else 0.0
    if known_sum <= 0:
        return (dict.fromkeys(known, 0.0), coverage)
    return ({factor_id: adjusted[factor_id] / known_sum for factor_id in known}, coverage)
