"""Tests for the fixed-order item selection (M8; spec/07 §2, roadmap "Twin Interview")."""

from __future__ import annotations

import pytest
from tests.support.preference_fixtures import INTERVIEW_BANK as BANK

from mindtrace.domain.ids import InterviewItemId
from mindtrace.engines.elicitation.select_fixed import (
    FIXED_SUFFIX_ORDER,
    fixed_prefix_order,
    full_fixed_order,
    next_item_id,
)


class TestFixedPrefixOrder:
    def test_returns_every_standard_pairwise_item_in_file_order(self) -> None:
        prefix = fixed_prefix_order(BANK)
        assert prefix == tuple(f"p{i:02d}" for i in range(1, 15))

    def test_excludes_consistency_check_repeats(self) -> None:
        prefix = fixed_prefix_order(BANK)
        assert "p03r" not in prefix
        assert "p07r" not in prefix


class TestFullFixedOrder:
    def test_covers_every_item_in_the_bank_exactly_once(self) -> None:
        order = full_fixed_order(BANK)
        assert len(order) == len(set(order))
        assert frozenset(order) == frozenset(BANK.item_ids)

    def test_prefix_then_suffix(self) -> None:
        order = full_fixed_order(BANK)
        assert order == fixed_prefix_order(BANK) + FIXED_SUFFIX_ORDER

    def test_a_consistency_check_repeat_never_precedes_its_original(self) -> None:
        order = full_fixed_order(BANK)
        assert order.index("p03") < order.index("p03r")
        assert order.index("p07") < order.index("p07r")

    def test_lands_within_the_banks_own_target_total_range(self) -> None:
        order = full_fixed_order(BANK)
        assert BANK.config.target_total_min <= len(order) <= BANK.config.target_total_max

    def test_raises_on_a_bank_version_mismatch_with_the_fixed_suffix(self) -> None:
        # Drop one disposition item so FIXED_SUFFIX_ORDER no longer exactly
        # matches the bank's actual disposition + consistency-check items -
        # a bank-version mismatch must be caught loudly, never silently
        # asking fewer/wrong items.
        mismatched = BANK.model_copy(update={"disposition": BANK.disposition[:-1]})
        with pytest.raises(ValueError, match="does not exactly cover"):
            full_fixed_order(mismatched)


class TestNextItemId:
    def test_first_call_returns_the_first_prefix_item(self) -> None:
        assert next_item_id(BANK, frozenset()) == "p01"

    def test_already_answered_items_are_excluded(self) -> None:
        answered = frozenset({InterviewItemId("p01"), InterviewItemId("p02")})
        assert next_item_id(BANK, answered) == "p03"

    def test_returns_none_once_every_item_is_answered(self) -> None:
        all_ids = frozenset(full_fixed_order(BANK))
        assert next_item_id(BANK, all_ids) is None

    def test_identical_input_gives_identical_output(self) -> None:
        answered = frozenset({InterviewItemId("p01")})
        assert next_item_id(BANK, answered) == next_item_id(BANK, answered)
