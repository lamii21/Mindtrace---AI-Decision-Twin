"""Golden tests for the confidence engine (M4 s19).

``docs/spec/06-confidence-model.md`` has no hand-worked numeric examples the
way spec §05 §9 does, so these are **implementation fixtures** - mathematically
transparent inputs built strictly from the documented formula, pinned the same
way M3's MCDA golden examples are, but not a claim of empirical accuracy
against a real user's history. Regenerate after a deliberate, reviewed change:

    MINDTRACE_GOLDEN_UPDATE=1 pytest tests/golden/test_confidence_golden.py -q
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from mindtrace.domain.confidence import ConfidenceResult
from mindtrace.engines.confidence.compute import compute_confidence
from tests.support.confidence_fixtures import (
    DECISION_EXAMPLE_1,
    DECISION_EXAMPLE_3,
    DECISION_EXAMPLE_5,
    DISAGREEING_ENSEMBLE,
    GENEROUS_N_EFF,
    UNANIMOUS_ENSEMBLE,
    WELL_CALIBRATED_LEDGER,
    self_consistency_signal,
)

DATA_DIR = Path(__file__).parent / "data" / "confidence_examples"
ABS_TOL = 1e-6


def _assert_matches_golden(name: str, result: ConfidenceResult) -> None:
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


class TestHighConfidence:
    """1. Every signal favourable and actually supplied: all five weights survive."""

    def test_matches_golden(self) -> None:
        result = compute_confidence(
            DECISION_EXAMPLE_1,
            n_eff=GENEROUS_N_EFF,
            ensemble=UNANIMOUS_ENSEMBLE,
            calibration=WELL_CALIBRATED_LEDGER,
            extraction=self_consistency_signal(1.0, DECISION_EXAMPLE_1),
        )
        assert result.value > 0.6
        assert set(result.weights_used) == {"A", "B", "C", "D", "E"}
        _assert_matches_golden("high_confidence", result)


class TestLowConfidence:
    """2. Cold start: no posterior, ensemble, ledger, or extraction data at all."""

    def test_matches_golden(self) -> None:
        result = compute_confidence(DECISION_EXAMPLE_1)
        assert result.value < DECISION_EXAMPLE_1.score  # C well below the strong S=0.69 lean
        _assert_matches_golden("low_confidence", result)


class TestMissingCalibration:
    """3. `calibration=None` -> term omitted, `calibrated="false"`, never a fabricated value."""

    def test_matches_golden(self) -> None:
        result = compute_confidence(DECISION_EXAMPLE_1, n_eff=GENEROUS_N_EFF)
        assert result.inputs.historical_calibration is None
        assert result.inputs.calibrated == "false"
        assert "C" not in result.weights_used
        _assert_matches_golden("missing_calibration", result)


class TestMissingExtractionSignal:
    """4. `extraction=None` -> `extraction_path="unavailable"`, distinct from the "single" path."""

    def test_matches_golden(self) -> None:
        result = compute_confidence(DECISION_EXAMPLE_1, n_eff=GENEROUS_N_EFF)
        assert result.inputs.extraction_path == "unavailable"
        assert result.inputs.extraction_entropy is None
        assert "D" not in result.weights_used
        _assert_matches_golden("missing_extraction", result)


class TestHighDisagreement:
    """5. A real ensemble that disagrees sharply pulls `C` down relative to a unanimous one."""

    def test_matches_golden(self) -> None:
        disagreeing = compute_confidence(
            DECISION_EXAMPLE_1, n_eff=GENEROUS_N_EFF, ensemble=DISAGREEING_ENSEMBLE
        )
        unanimous = compute_confidence(
            DECISION_EXAMPLE_1, n_eff=GENEROUS_N_EFF, ensemble=UNANIMOUS_ENSEMBLE
        )
        assert disagreeing.value < unanimous.value
        _assert_matches_golden("high_disagreement", disagreeing)


class TestLowEvidence:
    """6. Example 5's own low coverage (2/16 factors known) drives `evidence_sufficiency` down."""

    def test_matches_golden(self) -> None:
        result = compute_confidence(DECISION_EXAMPLE_5)
        assert result.inputs.coverage < 0.3
        assert result.inputs.evidence_sufficiency == 0.0
        _assert_matches_golden("low_evidence", result)


class TestThresholdBoundary:
    """7. Example 3's near-tie score keeps margin_adequacy at 0, pinning `C` near its floor."""

    def test_matches_golden(self) -> None:
        result = compute_confidence(DECISION_EXAMPLE_3)
        assert result.inputs.margin_adequacy == 0.0  # score is inside the dead zone
        _assert_matches_golden("threshold_boundary", result)


class TestConfidenceIndependentOfScore:
    """8. Two decisions with very different `S` but identical margin/coverage/weights inputs."""

    def test_matches_golden(self) -> None:
        flipped = DECISION_EXAMPLE_1.model_copy(
            update={"score": -DECISION_EXAMPLE_1.score, "raw_score": -DECISION_EXAMPLE_1.raw_score}
        )
        original = compute_confidence(DECISION_EXAMPLE_1, n_eff=GENEROUS_N_EFF)
        negated = compute_confidence(flipped, n_eff=GENEROUS_N_EFF)
        assert original.value == negated.value
        assert DECISION_EXAMPLE_1.score != flipped.score
        _assert_matches_golden("score_independence_original", original)
        _assert_matches_golden("score_independence_negated", negated)
