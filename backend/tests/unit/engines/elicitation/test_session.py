"""Tests for pure Twin Interview session-progress computations (M8)."""

from __future__ import annotations

from tests.support.preference_fixtures import INTERVIEW_BANK as BANK

from mindtrace.domain.ids import InterviewItemId
from mindtrace.engines.elicitation.select_fixed import full_fixed_order
from mindtrace.engines.elicitation.session import is_complete, progress_for

_FULL_ORDER = full_fixed_order(BANK)


class TestProgressFor:
    def test_zero_answers(self) -> None:
        progress = progress_for(BANK, frozenset())
        assert progress.answered == 0
        assert progress.target == len(_FULL_ORDER)

    def test_some_answers(self) -> None:
        answered = frozenset(_FULL_ORDER[:3])
        progress = progress_for(BANK, answered)
        assert progress.answered == 3
        assert progress.target == len(_FULL_ORDER)

    def test_all_answers(self) -> None:
        progress = progress_for(BANK, frozenset(_FULL_ORDER))
        assert progress.answered == progress.target

    def test_ignores_item_ids_outside_the_fixed_order(self) -> None:
        bogus = frozenset({InterviewItemId("not-a-real-item")})
        progress = progress_for(BANK, bogus)
        assert progress.answered == 0


class TestIsComplete:
    def test_false_when_no_items_answered(self) -> None:
        assert is_complete(BANK, frozenset()) is False

    def test_false_when_partially_answered(self) -> None:
        assert is_complete(BANK, frozenset(_FULL_ORDER[:-1])) is False

    def test_true_when_every_item_answered(self) -> None:
        assert is_complete(BANK, frozenset(_FULL_ORDER)) is True

    def test_extra_unknown_answers_do_not_fake_completion(self) -> None:
        answered = frozenset(_FULL_ORDER[:-1]) | {InterviewItemId("not-a-real-item")}
        assert is_complete(BANK, answered) is False
