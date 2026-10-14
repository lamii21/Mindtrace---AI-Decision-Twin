"""Tests for ensemble disagreement diagnostics (M10; ADR-007)."""

from __future__ import annotations

import pytest
from tests.support.twin_fixtures import twin_result_with

from mindtrace.domain.decision import Contribution
from mindtrace.domain.enums import DecisionOutcome, ScaleLevel
from mindtrace.domain.ids import FactorId
from mindtrace.domain.simulation import TwinConfigResult
from mindtrace.engines.debate.disagreement import conflict_axis, label_consensus


class TestLabelConsensus:
    def test_all_same_label_is_unanimous(self) -> None:
        labels = [DecisionOutcome.ACCEPT] * 5
        assert label_consensus(labels) == "unanimous"

    def test_strict_majority_is_majority(self) -> None:
        labels = [DecisionOutcome.ACCEPT] * 3 + [DecisionOutcome.REJECT] * 2
        assert label_consensus(labels) == "majority"

    def test_no_strict_majority_is_split(self) -> None:
        labels = [DecisionOutcome.ACCEPT, DecisionOutcome.ACCEPT, DecisionOutcome.REJECT]
        # 2/3 is NOT a tie, but 2 of 4 would be a tie - construct a real tie case
        tied = [DecisionOutcome.ACCEPT, DecisionOutcome.ACCEPT, DecisionOutcome.REJECT]
        tied += [DecisionOutcome.REJECT]
        assert label_consensus(tied) == "split"
        # sanity: the 3-vs-2 case above IS a majority, not split
        assert label_consensus(labels) == "majority"

    def test_single_label_is_unanimous(self) -> None:
        assert label_consensus([DecisionOutcome.UNCERTAIN]) == "unanimous"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            label_consensus([])


class TestConflictAxis:
    def test_fewer_than_two_twins_is_empty(self) -> None:
        result = twin_result_with(twin="base", contributions={})
        assert conflict_axis([result]) == ()

    def test_empty_when_no_twin_has_any_contribution(self) -> None:
        results = [
            twin_result_with(twin="base", contributions={}),
            twin_result_with(twin="career", contributions={}),
        ]
        assert conflict_axis(results) == ()

    def test_matches_a_hand_computed_variance(self) -> None:
        """ADR-007's own named test: conflict_axis matches a hand-computed variance."""
        results = [
            twin_result_with(twin="base", contributions={"skill_growth": 0.1, "stability": 0.2}),
            twin_result_with(twin="career", contributions={"skill_growth": 0.5, "stability": 0.21}),
            twin_result_with(twin="safe", contributions={"skill_growth": -0.1, "stability": 0.19}),
        ]
        # skill_growth: [0.1, 0.5, -0.1] -> high variance
        # stability:    [0.2, 0.21, 0.19] -> near-zero variance
        skill_growth_values = [0.1, 0.5, -0.1]
        stability_values = [0.2, 0.21, 0.19]
        mean_sg = sum(skill_growth_values) / 3
        mean_st = sum(stability_values) / 3
        var_sg = sum((v - mean_sg) ** 2 for v in skill_growth_values) / 3
        var_st = sum((v - mean_st) ** 2 for v in stability_values) / 3
        assert var_sg > var_st  # sanity: the hand computation itself is as expected
        assert conflict_axis(results) == (FactorId("skill_growth"),)

    def test_ties_report_every_tied_factor_sorted(self) -> None:
        results = [
            twin_result_with(twin="base", contributions={"skill_growth": 0.0, "stability": 0.0}),
            twin_result_with(twin="career", contributions={"skill_growth": 1.0, "stability": 1.0}),
        ]
        assert conflict_axis(results) == (FactorId("skill_growth"), FactorId("stability"))

    def test_a_factor_missing_from_some_twins_is_still_handled(self) -> None:
        results = [
            twin_result_with(twin="base", contributions={"skill_growth": 0.1}),
            twin_result_with(twin="career", contributions={"skill_growth": 0.5, "stability": 0.9}),
        ]
        assert conflict_axis(results) == (FactorId("skill_growth"),)


def test_contribution_helper_shape_sanity() -> None:
    """A guard on the shared fixture helper, not the engine itself."""
    result = twin_result_with(twin="base", contributions={"skill_growth": 0.3})
    assert isinstance(result, TwinConfigResult)
    contribution = result.decision.contributions[0]
    assert isinstance(contribution, Contribution)
    assert contribution.level_a is ScaleLevel.HIGH
