"""The MCDA engine's public entry points: `decide` (binary) and `decide_multi_option`.

Pure orchestration over ``normalize.py``/``aggregate.py``: no I/O, no clock, no
randomness, no persistence, no LLM. ``docs/spec/05-mcda-mathematics.md`` §5's
decision rule has three gates in priority order - coverage, confidence,
score-band (see that spec's corrected §5 note) - and this module implements
exactly the first and the third. The confidence gate is not a stub: `C` does
not exist in M3, so there is nothing here pretending to compute it. A later
milestone composes this module's `label`/`uncertain_reason` with a real `C` in
one small, separate step; it never needs to touch this file.
"""

from __future__ import annotations

from collections.abc import Sequence

from mindtrace.domain.decision import (
    Contribution,
    DecisionResult,
    DispositionInputs,
    FactorVector,
    WeightVector,
)
from mindtrace.domain.enums import DecisionOutcome, ScaleLevel, UncertainReason
from mindtrace.domain.factors import FactorTaxonomy
from mindtrace.domain.ids import FactorId
from mindtrace.engines.mcda.aggregate import (
    aggregate_value,
    contribution_percentages,
    decision_score,
    factor_contributions,
)
from mindtrace.engines.mcda.config import DEFAULT_MCDA_CONFIG, ENGINE_VERSION, MCDAConfig
from mindtrace.engines.mcda.errors import MCDAValidationError
from mindtrace.engines.mcda.normalize import adjust_weights, normalize_factor, renormalize_known

MIN_MULTI_OPTION_COUNT = 3


def decide(
    taxonomy: FactorTaxonomy,
    weights: WeightVector,
    factors_a: FactorVector,
    dispositions: DispositionInputs,
    *,
    factors_b: FactorVector | None = None,
    config: MCDAConfig = DEFAULT_MCDA_CONFIG,
) -> DecisionResult:
    """Score option `A` against the status-quo baseline (or an explicitly described `B`).

    Raises:
        MCDAValidationError: if `weights` does not cover exactly the
            taxonomy's core factors, or `factors_a`/`factors_b` reference a
            factor outside the taxonomy's core+extended set.
    """
    _validate_weights_cover_taxonomy(weights, taxonomy)
    _validate_factor_vector(factors_a, taxonomy, label="factors_a")
    if factors_b is not None:
        _validate_factor_vector(factors_b, taxonomy, label="factors_b")

    known = factors_a.known_ids()
    w_adj = adjust_weights(weights.weights, dispositions, config)
    w_known, coverage = renormalize_known(w_adj, known)

    levels_a = {factor_id: _level_of(factors_a, factor_id) for factor_id in known}
    n_a = {
        factor_id: normalize_factor(
            taxonomy.get(factor_id),
            taxonomy.get(factor_id).anchor_for(levels_a[factor_id]),
            dispositions,
            config,
        )
        for factor_id in known
    }
    n_b = {
        factor_id: _baseline_or_described(factor_id, factors_b, taxonomy, dispositions, config)
        for factor_id in known
    }

    return _assemble_result(
        w_known=w_known,
        coverage=coverage,
        n_a=n_a,
        n_b=n_b,
        levels_a=levels_a,
        dispositions=dispositions,
        config=config,
        known=known,
        total_factor_count=len(taxonomy.core_ids),
    )


def decide_multi_option(
    taxonomy: FactorTaxonomy,
    weights: WeightVector,
    options: Sequence[tuple[str, FactorVector]],
    dispositions: DispositionInputs,
    *,
    config: MCDAConfig = DEFAULT_MCDA_CONFIG,
) -> DecisionResult:
    """Rank 3+ options with no natural status quo; pick the best against the runner-up (spec §8).

    Every option must declare `known=True` for exactly the same set of factor
    ids - the spec does not define how to compare options extracted with
    different coverage, so this requires them to match rather than guessing a
    cross-option blending rule (documented interpretation; see M3's final
    report). There is never a `REJECT` label here, only `ACCEPT` (meaning
    "pick `selected_option`") or `UNCERTAIN`, per spec §8.

    Raises:
        MCDAValidationError: if fewer than 3 options are given, if any two
            options have different known-factor sets, or the taxonomy/weight
            checks from :func:`decide` fail.
    """
    if len(options) < MIN_MULTI_OPTION_COUNT:
        msg = (
            f"decide_multi_option requires >= {MIN_MULTI_OPTION_COUNT} options, got {len(options)}"
        )
        raise MCDAValidationError(msg)

    _validate_weights_cover_taxonomy(weights, taxonomy)
    for option_label, factor_vector in options:
        _validate_factor_vector(factor_vector, taxonomy, label=option_label)

    known = options[0][1].known_ids()
    for option_label, factor_vector in options[1:]:
        if factor_vector.known_ids() != known:
            msg = (
                f"option {option_label!r} has a different known-factor set than "
                f"{options[0][0]!r}; decide_multi_option requires identical coverage "
                "across all options"
            )
            raise MCDAValidationError(msg)

    w_adj = adjust_weights(weights.weights, dispositions, config)
    w_known, coverage = renormalize_known(w_adj, known)

    values: dict[str, dict[FactorId, float]] = {}
    levels: dict[str, dict[FactorId, ScaleLevel]] = {}
    aggregates: dict[str, float] = {}
    for option_label, factor_vector in options:
        option_levels = {factor_id: _level_of(factor_vector, factor_id) for factor_id in known}
        n = {
            factor_id: normalize_factor(
                taxonomy.get(factor_id),
                taxonomy.get(factor_id).anchor_for(option_levels[factor_id]),
                dispositions,
                config,
            )
            for factor_id in known
        }
        values[option_label] = n
        levels[option_label] = option_levels
        aggregates[option_label] = aggregate_value(w_known, n)

    ranked = sorted(options, key=lambda item: aggregates[item[0]], reverse=True)
    winner_label = ranked[0][0]
    runner_up_label = ranked[1][0]

    return _assemble_result(
        w_known=w_known,
        coverage=coverage,
        n_a=values[winner_label],
        n_b=values[runner_up_label],
        levels_a=levels[winner_label],
        dispositions=dispositions,
        config=config,
        known=known,
        total_factor_count=len(taxonomy.core_ids),
        multi_option_winner=winner_label,
    )


def _assemble_result(
    *,
    w_known: dict[FactorId, float],
    coverage: float,
    n_a: dict[FactorId, float],
    n_b: dict[FactorId, float],
    levels_a: dict[FactorId, ScaleLevel],
    dispositions: DispositionInputs,
    config: MCDAConfig,
    known: tuple[FactorId, ...],
    total_factor_count: int,
    multi_option_winner: str | None = None,
) -> DecisionResult:
    v_a = aggregate_value(w_known, n_a)
    v_b = aggregate_value(w_known, n_b)
    raw_score, score = decision_score(v_a, v_b, config)

    is_multi_option = multi_option_winner is not None
    raw_label = _raw_label(score, config, allow_reject=not is_multi_option)

    coverage_min_user = (
        config.coverage_min + config.ambiguity_coverage_slope * dispositions.ambiguity_aversion
    )

    # Gate priority, corrected in spec/05 s5: coverage, then confidence (not computed in M3,
    # so never gates here), then the score-band fallback.
    label: DecisionOutcome
    uncertain_reason: UncertainReason | None
    if coverage < coverage_min_user:
        label, uncertain_reason = DecisionOutcome.UNCERTAIN, UncertainReason.INSUFFICIENT_COVERAGE
    elif raw_label is DecisionOutcome.UNCERTAIN:
        label, uncertain_reason = DecisionOutcome.UNCERTAIN, UncertainReason.SCORE_IN_BAND
    else:
        label, uncertain_reason = raw_label, None

    margin = abs(score) - config.tau_accept
    raw_contributions = factor_contributions(w_known, n_a, n_b, config)
    percentages = contribution_percentages(raw_contributions)

    contributions = tuple(
        sorted(
            (
                Contribution(
                    factor_id=factor_id,
                    level_a=levels_a[factor_id],
                    weight=w_known[factor_id],
                    normalized_value_a=n_a[factor_id],
                    normalized_value_b=n_b[factor_id],
                    raw_contribution=raw_contributions[factor_id],
                    contribution_pct=percentages[factor_id],
                )
                for factor_id in known
            ),
            key=lambda c: (-abs(c.contribution_pct), c.factor_id),
        )
    )

    selected_option = multi_option_winner if label is DecisionOutcome.ACCEPT else None

    return DecisionResult(
        engine_version=ENGINE_VERSION,
        config_version=config.version,
        score=score,
        raw_score=raw_score,
        raw_label=raw_label,
        label=label,
        uncertain_reason=uncertain_reason,
        coverage=coverage,
        margin=margin,
        known_factor_count=len(known),
        total_factor_count=total_factor_count,
        contributions=contributions,
        selected_option=selected_option,
    )


def _raw_label(score: float, config: MCDAConfig, *, allow_reject: bool) -> DecisionOutcome:
    if score >= config.tau_accept:
        return DecisionOutcome.ACCEPT
    if allow_reject and score <= config.tau_reject:
        return DecisionOutcome.REJECT
    return DecisionOutcome.UNCERTAIN


def _level_of(factors: FactorVector, factor_id: FactorId) -> ScaleLevel:
    reading = factors.readings[factor_id]
    if reading.level is None:  # pragma: no cover - guaranteed by FactorReading's own validator
        msg = f"factor {factor_id!r} is marked known but carries no level"
        raise MCDAValidationError(msg)
    return reading.level


def _baseline_or_described(
    factor_id: FactorId,
    factors_b: FactorVector | None,
    taxonomy: FactorTaxonomy,
    dispositions: DispositionInputs,
    config: MCDAConfig,
) -> float:
    if factors_b is not None:
        reading = factors_b.readings.get(factor_id)
        if reading is not None and reading.known:
            spec = taxonomy.get(factor_id)
            level = _level_of(factors_b, factor_id)
            return normalize_factor(spec, spec.anchor_for(level), dispositions, config)
    return config.baseline_n


def _validate_weights_cover_taxonomy(weights: WeightVector, taxonomy: FactorTaxonomy) -> None:
    expected = set(taxonomy.core_ids)
    actual = set(weights.weights)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        msg = (
            "weights must cover exactly the taxonomy's core factors; "
            f"missing={missing}, extra={extra}"
        )
        raise MCDAValidationError(msg)


def _validate_factor_vector(factors: FactorVector, taxonomy: FactorTaxonomy, *, label: str) -> None:
    unknown_ids = sorted(fid for fid in factors.readings if fid not in taxonomy)
    if unknown_ids:
        msg = f"{label} references factor ids outside the taxonomy: {unknown_ids}"
        raise MCDAValidationError(msg)
    non_core = sorted(fid for fid in factors.readings if fid not in taxonomy.core_ids)
    if non_core:
        msg = f"{label} references non-core (extended) factor ids, not aggregated in v1: {non_core}"
        raise MCDAValidationError(msg)
