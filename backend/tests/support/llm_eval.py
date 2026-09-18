"""Evaluation harness for `tests/support/data/llm_eval_dataset.json` (M5 §14)
and paraphrase-consistency comparison utilities (M5 §13).

Nothing here is called by production code - this is test/evaluation tooling
only, kept in `tests/support/` rather than `src/mindtrace/llm/` for exactly
that reason. No metric computed here is claimed as a measurement of any real
provider's accuracy: with no real provider available in this environment,
every "accuracy" number this harness can currently produce is a harness
self-check (does the metric arithmetic work?), not a benchmark result - see
`tests/unit/llm/test_eval_dataset.py` for how that distinction is enforced in
the test suite itself.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from mindtrace.domain.decision import FactorVector
from mindtrace.domain.ids import FactorId
from mindtrace.llm.schema import ExtractionOutcome

_DATASET_PATH = Path(__file__).parent / "data" / "llm_eval_dataset.json"


@dataclass(frozen=True)
class EvalScenario:
    """One labelled evaluation scenario."""

    id: str
    category: str
    scenario: str
    gold_factors: dict[FactorId, str]
    notes: str
    paraphrase_cluster: int | None = None


def load_eval_dataset(path: Path = _DATASET_PATH) -> list[EvalScenario]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        EvalScenario(
            id=entry["id"],
            category=entry["category"],
            scenario=entry["scenario"],
            gold_factors={FactorId(k): v for k, v in entry["gold_factors"].items()},
            notes=entry["notes"],
            paraphrase_cluster=entry.get("paraphrase_cluster"),
        )
        for entry in raw
    ]


@dataclass(frozen=True)
class EvalMetrics:
    """Aggregate metrics over one evaluation run (M5 §14).

    Every field that cannot be meaningfully computed without a real provider
    is `None`, never a fabricated number - callers must check for `None`
    before reporting a metric (`measured` reflects exactly which fields are).
    """

    total_scenarios: int
    rejected_count: int  # ExtractionOutcome.status == "failed"
    factor_identification_accuracy: float | None
    level_accuracy: float | None
    ambiguous_correctly_unknown_rate: float | None
    adversarial_no_factors_rate: float | None
    measured: frozenset[str] = field(default_factory=frozenset)


def factor_identification_accuracy(
    scenarios: Sequence[EvalScenario], outcomes: Sequence[ExtractionOutcome]
) -> float:
    """Fraction of gold-labelled factors the outcome also reports as `known`."""
    total = 0
    correct = 0
    for scenario, outcome in zip(scenarios, outcomes, strict=True):
        for factor_id in scenario.gold_factors:
            total += 1
            if factor_id in outcome.factors.known_ids():
                correct += 1
    return correct / total if total else 1.0


def level_accuracy(
    scenarios: Sequence[EvalScenario], outcomes: Sequence[ExtractionOutcome]
) -> float:
    """Of the gold factors the outcome correctly identified as known, the fraction
    whose extracted level exactly matches the gold level."""
    total = 0
    correct = 0
    for scenario, outcome in zip(scenarios, outcomes, strict=True):
        for factor_id, gold_level in scenario.gold_factors.items():
            reading = outcome.factors.readings.get(factor_id)
            if reading is None or not reading.known:
                continue
            total += 1
            if reading.level is not None and reading.level.value == gold_level:
                correct += 1
    return correct / total if total else 1.0


def ambiguous_correctly_unknown_rate(
    scenarios: Sequence[EvalScenario], outcomes: Sequence[ExtractionOutcome]
) -> float:
    """Of scenarios whose gold label is "no real evidence" (`gold_factors={}`),
    the fraction the outcome also reports with zero known factors."""
    relevant = [(s, o) for s, o in zip(scenarios, outcomes, strict=True) if not s.gold_factors]
    if not relevant:
        return 1.0
    correct = sum(1 for _, outcome in relevant if outcome.factors.known_ids() == ())
    return correct / len(relevant)


def adversarial_no_factors_rate(
    scenarios: Sequence[EvalScenario], outcomes: Sequence[ExtractionOutcome]
) -> float:
    """Of `category == "adversarial"` scenarios, the fraction that end up with zero
    known factors - an injection attempt describes no real decision, so a
    correctly-behaving pipeline never extracts anything from it."""
    relevant = [
        (s, o) for s, o in zip(scenarios, outcomes, strict=True) if s.category == "adversarial"
    ]
    if not relevant:
        return 1.0
    correct = sum(1 for _, outcome in relevant if outcome.factors.known_ids() == ())
    return correct / len(relevant)


def compute_eval_metrics(
    scenarios: Sequence[EvalScenario], outcomes: Sequence[ExtractionOutcome]
) -> EvalMetrics:
    rejected = sum(1 for outcome in outcomes if outcome.status == "failed")
    return EvalMetrics(
        total_scenarios=len(scenarios),
        rejected_count=rejected,
        factor_identification_accuracy=factor_identification_accuracy(scenarios, outcomes),
        level_accuracy=level_accuracy(scenarios, outcomes),
        ambiguous_correctly_unknown_rate=ambiguous_correctly_unknown_rate(scenarios, outcomes),
        adversarial_no_factors_rate=adversarial_no_factors_rate(scenarios, outcomes),
        measured=frozenset(
            {
                "factor_identification_accuracy",
                "level_accuracy",
                "ambiguous_correctly_unknown_rate",
                "adversarial_no_factors_rate",
            }
        ),
    )


# --- Paraphrase consistency (M5 s13) ----------------------------------------


@dataclass(frozen=True)
class ParaphraseDiff:
    """What changed between two validated extractions of paraphrased scenarios."""

    changed_known_status: frozenset[FactorId]
    changed_levels: frozenset[FactorId]
    became_uncertain: frozenset[FactorId]  # known in `a`, unknown in `b`
    became_known: frozenset[FactorId]  # unknown in `a`, known in `b`


def diff_extractions(a: FactorVector, b: FactorVector) -> ParaphraseDiff:
    """Compare two validated `FactorVector`s - never a "semantic similarity" score,
    only concrete, individually-listable differences (M5 §13)."""
    all_ids = set(a.readings) | set(b.readings)
    changed_known_status: set[FactorId] = set()
    changed_levels: set[FactorId] = set()
    became_uncertain: set[FactorId] = set()
    became_known: set[FactorId] = set()

    for factor_id in all_ids:
        reading_a = a.readings.get(factor_id)
        reading_b = b.readings.get(factor_id)
        known_a = reading_a is not None and reading_a.known
        known_b = reading_b is not None and reading_b.known

        if known_a != known_b:
            changed_known_status.add(factor_id)
            if known_a and not known_b:
                became_uncertain.add(factor_id)
            if known_b and not known_a:
                became_known.add(factor_id)
        elif known_a and known_b:
            assert reading_a is not None
            assert reading_b is not None
            if reading_a.level != reading_b.level:
                changed_levels.add(factor_id)

    return ParaphraseDiff(
        changed_known_status=frozenset(changed_known_status),
        changed_levels=frozenset(changed_levels),
        became_uncertain=frozenset(became_uncertain),
        became_known=frozenset(became_known),
    )


def paraphrase_clusters(scenarios: Sequence[EvalScenario]) -> dict[int, list[EvalScenario]]:
    clusters: dict[int, list[EvalScenario]] = {}
    for scenario in scenarios:
        if scenario.paraphrase_cluster is not None:
            clusters.setdefault(scenario.paraphrase_cluster, []).append(scenario)
    return clusters
