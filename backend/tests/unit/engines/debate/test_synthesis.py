"""Tests for the deterministic weight-of-evidence synthesis vote (M10; ADR-007)."""

from __future__ import annotations

import pytest
from tests.support.twin_fixtures import twin_result_with

from mindtrace.domain.enums import DecisionOutcome
from mindtrace.domain.simulation import TwinConfigResult
from mindtrace.engines.debate.synthesis import BASE_TWIN_VOTE_WEIGHT, synthesize


def _results(**labels: DecisionOutcome) -> list[TwinConfigResult]:
    return [
        twin_result_with(twin=twin, contributions={}, label=label) for twin, label in labels.items()
    ]


class TestSynthesize:
    def test_unanimous_vote_wins(self) -> None:
        results = _results(
            base=DecisionOutcome.ACCEPT,
            career=DecisionOutcome.ACCEPT,
            safe=DecisionOutcome.ACCEPT,
        )
        synthesis = synthesize(results)
        assert synthesis.recommended_label is DecisionOutcome.ACCEPT
        assert synthesis.margin == pytest.approx(1.0)
        assert synthesis.label_consensus == "unanimous"

    def test_base_twin_counts_double(self) -> None:
        """base=REJECT (weight 2) vs. 2 other twins voting ACCEPT (weight 1 each) -> tied 2-2."""
        results = _results(
            base=DecisionOutcome.REJECT,
            career=DecisionOutcome.ACCEPT,
            safe=DecisionOutcome.ACCEPT,
        )
        synthesis = synthesize(results)
        # tied 2-2: REJECT wins the tie-break (alphabetically before "ACCEPT"? no -
        # "ACCEPT" < "REJECT" lexically, so ACCEPT wins the tie per the documented
        # deterministic tie-break rule) - assert the tie, not a specific winner here.
        assert synthesis.margin == pytest.approx(0.0)
        assert synthesis.vote_tally["REJECT"] == BASE_TWIN_VOTE_WEIGHT
        assert synthesis.vote_tally["ACCEPT"] == 2.0

    def test_base_twin_alone_can_still_outvote_a_minority_of_others(self) -> None:
        """base=ACCEPT (weight 2) vs. 1 other twin voting REJECT (weight 1) -> ACCEPT wins 2-1."""
        results = _results(base=DecisionOutcome.ACCEPT, career=DecisionOutcome.REJECT)
        synthesis = synthesize(results)
        assert synthesis.recommended_label is DecisionOutcome.ACCEPT
        assert synthesis.margin == pytest.approx(1.0 / 3.0)

    def test_a_majority_of_other_twins_can_outvote_the_base_twin(self) -> None:
        """base=ACCEPT (weight 2) vs 3 others voting REJECT (weight 1 each) -> REJECT wins 3-2."""
        results = _results(
            base=DecisionOutcome.ACCEPT,
            career=DecisionOutcome.REJECT,
            safe=DecisionOutcome.REJECT,
            dream=DecisionOutcome.REJECT,
        )
        synthesis = synthesize(results)
        assert synthesis.recommended_label is DecisionOutcome.REJECT
        assert synthesis.vote_tally["ACCEPT"] == BASE_TWIN_VOTE_WEIGHT
        assert synthesis.vote_tally["REJECT"] == 3.0

    def test_vote_tally_only_includes_labels_that_actually_occurred(self) -> None:
        results = _results(base=DecisionOutcome.ACCEPT, career=DecisionOutcome.ACCEPT)
        synthesis = synthesize(results)
        assert set(synthesis.vote_tally) == {"ACCEPT"}

    def test_synthesis_version_is_a_stable_string(self) -> None:
        results = _results(base=DecisionOutcome.ACCEPT)
        synthesis = synthesize(results)
        assert isinstance(synthesis.synthesis_version, str)
        assert synthesis.synthesis_version

    def test_empty_results_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            synthesize([])

    def test_missing_base_twin_raises(self) -> None:
        results = _results(career=DecisionOutcome.ACCEPT, safe=DecisionOutcome.REJECT)
        with pytest.raises(ValueError, match="base"):
            synthesize(results)

    def test_more_than_one_base_twin_raises(self) -> None:
        results = [
            twin_result_with(twin="base", contributions={}, label=DecisionOutcome.ACCEPT),
            twin_result_with(twin="base", contributions={}, label=DecisionOutcome.REJECT),
        ]
        with pytest.raises(ValueError, match="base"):
            synthesize(results)

    def test_deterministic(self) -> None:
        results = _results(
            base=DecisionOutcome.ACCEPT,
            career=DecisionOutcome.REJECT,
            safe=DecisionOutcome.UNCERTAIN,
        )
        first = synthesize(results)
        second = synthesize(results)
        assert first == second
