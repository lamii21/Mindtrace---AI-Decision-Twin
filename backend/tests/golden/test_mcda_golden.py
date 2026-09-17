"""Golden tests: the five hand-worked examples in ``docs/spec/05-mcda-mathematics.md`` §9.

Each test asserts both the *readable* numbers a person checking against the
spec would look for (score, label, top contribution) and, via the pinned JSON
file, every other field to a tight tolerance - so an accidental change to the
mathematics shows up as a failing test, not a silent drift (M3 s6/s19).

Regenerate the pinned JSON after a deliberate, reviewed change to the engine:

    MINDTRACE_GOLDEN_UPDATE=1 pytest tests/golden/test_mcda_golden.py -q
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import pytest

from mindtrace.domain.decision import DecisionResult, FactorVector, WeightVector
from mindtrace.domain.enums import DecisionOutcome, UncertainReason
from mindtrace.engines.mcda.decide import decide
from tests.support.mcda_fixtures import (
    EXAMPLE_1_FACTORS,
    EXAMPLE_2_FACTORS,
    EXAMPLE_3_FACTORS,
    EXAMPLE_4_FACTORS,
    EXAMPLE_5_FACTORS,
    T_REF_DISPOSITIONS,
    T_REF_WEIGHTS,
    TAXONOMY,
    factor_vector,
)

DATA_DIR = Path(__file__).parent / "data" / "mcda_examples"
ABS_TOL = 1e-6


def _run(factors: FactorVector) -> DecisionResult:
    return decide(TAXONOMY, T_REF_WEIGHTS, factors, T_REF_DISPOSITIONS)


def _assert_matches_golden(name: str, result: DecisionResult) -> None:
    path = DATA_DIR / f"{name}.json"
    actual = json.loads(result.model_dump_json())

    if os.environ.get("MINDTRACE_GOLDEN_UPDATE") == "1":
        path.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return

    assert path.exists(), f"{path} is missing - generate it once with MINDTRACE_GOLDEN_UPDATE=1"
    expected = json.loads(path.read_text(encoding="utf-8"))
    _assert_deep_close(actual, expected, path=name)


def _assert_deep_close(actual: Any, expected: Any, *, path: str) -> None:
    if isinstance(expected, dict):
        assert isinstance(actual, dict), path
        assert actual.keys() == expected.keys(), path
        for key in expected:
            _assert_deep_close(actual[key], expected[key], path=f"{path}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list), path
        assert len(actual) == len(expected), path
        for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
            _assert_deep_close(a, e, path=f"{path}[{i}]")
    elif isinstance(expected, float):
        assert math.isclose(actual, expected, abs_tol=ABS_TOL, rel_tol=0), (
            f"{path}: {actual!r} != {expected!r}"
        )
    else:
        assert actual == expected, path


class TestExample1ClearAccept:
    """spec/05 s9 Example 1: S=0.690, ACCEPT, skill_growth the largest contributor at +38.9%."""

    def test_matches_spec_headline_numbers(self) -> None:
        result = _run(EXAMPLE_1_FACTORS)
        assert result.label is DecisionOutcome.ACCEPT
        assert result.uncertain_reason is None
        assert math.isclose(result.score, 0.690, abs_tol=1e-3)
        assert math.isclose(result.margin, 0.490, abs_tol=1e-3)
        top = result.contributions[0]
        assert top.factor_id == "skill_growth"
        assert math.isclose(top.contribution_pct, 38.9, abs_tol=0.1)

    def test_every_contribution_pct_matches_spec_to_one_decimal(self) -> None:
        expected = {
            "skill_growth": 38.9,
            "location_fit": 17.7,
            "financial_return": 12.4,
            "downside_risk": 12.2,
            "financial_security": 10.0,
            "intrinsic_interest": 8.8,
        }
        result = _run(EXAMPLE_1_FACTORS)
        actual = {str(c.factor_id): c.contribution_pct for c in result.contributions}
        assert actual.keys() == expected.keys()
        for factor_id, expected_pct in expected.items():
            assert math.isclose(actual[factor_id], expected_pct, abs_tol=0.1), factor_id

    def test_contributions_sum_to_100_and_full_trace_matches_golden(self) -> None:
        result = _run(EXAMPLE_1_FACTORS)
        total_pct = sum(c.contribution_pct for c in result.contributions)
        assert math.isclose(total_pct, 100.0, abs_tol=1e-6)
        _assert_matches_golden("example_1", result)


class TestExample2ClearReject:
    """spec/05 s9 Example 2: S=-0.859, REJECT, financial_return the largest (negative)."""

    def test_matches_spec_headline_numbers(self) -> None:
        result = _run(EXAMPLE_2_FACTORS)
        assert result.label is DecisionOutcome.REJECT
        assert result.uncertain_reason is None
        assert math.isclose(result.score, -0.859, abs_tol=1e-3)
        assert math.isclose(result.margin, 0.659, abs_tol=1e-3)
        top = result.contributions[0]
        assert top.factor_id == "financial_return"
        assert math.isclose(top.contribution_pct, -23.9, abs_tol=0.1)

    def test_every_contribution_pct_matches_spec_to_one_decimal(self) -> None:
        expected = {
            "financial_return": -23.9,
            "downside_risk": -20.9,
            "skill_growth": -16.4,
            "financial_security": -14.9,
            "location_fit": -14.9,
            "stability": -9.0,
        }
        result = _run(EXAMPLE_2_FACTORS)
        actual = {str(c.factor_id): c.contribution_pct for c in result.contributions}
        assert actual.keys() == expected.keys()
        for factor_id, expected_pct in expected.items():
            assert math.isclose(actual[factor_id], expected_pct, abs_tol=0.1), factor_id

    def test_contributions_sum_to_minus_100_and_full_trace_matches_golden(self) -> None:
        result = _run(EXAMPLE_2_FACTORS)
        total_pct = sum(c.contribution_pct for c in result.contributions)
        assert math.isclose(total_pct, -100.0, abs_tol=1e-6)
        _assert_matches_golden("example_2", result)


class TestExample3NearTie:
    """spec/05 s9 Example 3: S=0.127, UNCERTAIN/score_in_band - positive lean, not enough."""

    def test_matches_spec_headline_numbers(self) -> None:
        result = _run(EXAMPLE_3_FACTORS)
        assert result.label is DecisionOutcome.UNCERTAIN
        assert result.uncertain_reason is UncertainReason.SCORE_IN_BAND
        assert math.isclose(result.score, 0.127, abs_tol=1e-3)
        assert result.margin < 0  # inside the dead zone, per spec

    def test_full_trace_matches_golden(self) -> None:
        result = _run(EXAMPLE_3_FACTORS)
        _assert_matches_golden("example_3", result)


class TestExample4ConflictingFactorsLowMargin:
    """spec/05 s9 Example 4: S=0.323, ACCEPT at low margin (0.123)."""

    def test_matches_spec_headline_numbers(self) -> None:
        result = _run(EXAMPLE_4_FACTORS)
        assert result.label is DecisionOutcome.ACCEPT
        assert math.isclose(result.score, 0.323, abs_tol=1e-3)
        assert math.isclose(result.margin, 0.123, abs_tol=1e-3)
        top = result.contributions[0]
        assert top.factor_id == "skill_growth"
        assert math.isclose(top.contribution_pct, 34.3, abs_tol=0.1)

    def test_dropping_reversibility_flips_to_uncertain(self) -> None:
        # spec/05 s9 Example 4's own "what would flip this?" note: dropping
        # reversibility gives "S ~ 0.18" -> UNCERTAIN. That number is reproduced
        # exactly with reversibility=very_low (0.183993); the prose's "low" is a
        # colloquial description of the drop, not the literal ScaleLevel.LOW enum
        # member (which alone still clears TAU_ACCEPT at S=0.218877 - verified
        # empirically, not a spec bug).
        flipped = factor_vector(
            {
                "skill_growth": "very_high",
                "autonomy": "very_high",
                "intrinsic_interest": "very_high",
                "financial_return": "low",
                "financial_security": "low",
                "downside_risk": "high",
                "reversibility": "very_low",
            }
        )
        result = _run(flipped)
        assert math.isclose(result.score, 0.184, abs_tol=1e-3)
        assert result.label is DecisionOutcome.UNCERTAIN
        assert result.uncertain_reason is UncertainReason.SCORE_IN_BAND

    def test_full_trace_matches_golden(self) -> None:
        result = _run(EXAMPLE_4_FACTORS)
        _assert_matches_golden("example_4", result)


class TestExample5InsufficientEvidence:
    """spec/05 s9 Example 5: only 2/16 known, UNCERTAIN/insufficient_coverage, S ~ 0."""

    def test_matches_spec_headline_numbers(self) -> None:
        result = _run(EXAMPLE_5_FACTORS)
        assert result.label is DecisionOutcome.UNCERTAIN
        assert result.uncertain_reason is UncertainReason.INSUFFICIENT_COVERAGE
        assert result.known_factor_count == 2
        assert result.total_factor_count == 16
        assert math.isclose(result.score, -0.007, abs_tol=1e-2)

    def test_full_trace_matches_golden(self) -> None:
        result = _run(EXAMPLE_5_FACTORS)
        _assert_matches_golden("example_5", result)


def test_t_ref_weight_table_bug_is_fixed_and_documented() -> None:
    """The corrected T_REF_WEIGHTS sums to exactly 1.0 - the bug spec/05 s9's note documents."""
    total = sum(T_REF_WEIGHTS.weights.values())
    assert math.isclose(total, 1.0, abs_tol=1e-9)


def test_dispositions_are_the_published_t_ref() -> None:
    assert T_REF_DISPOSITIONS.risk_tolerance == 0.35
    assert T_REF_DISPOSITIONS.time_discount == 0.5
    assert T_REF_DISPOSITIONS.ambiguity_aversion == 0.5
    assert T_REF_DISPOSITIONS.effort_tolerance == 0.5


@pytest.mark.golden
def test_weight_vector_is_the_documented_shape() -> None:
    assert isinstance(T_REF_WEIGHTS, WeightVector)
