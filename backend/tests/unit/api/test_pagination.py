"""Tests for `mindtrace.api.pagination`."""

from __future__ import annotations

from mindtrace.api.pagination import paginate


def _sort_key(item: tuple[str, int]) -> tuple[str, str]:
    return item[0], str(item[1])


class TestPaginate:
    def test_first_page_returns_up_to_limit_items_in_order(self) -> None:
        items = [("2026-01-0" + str(i), i) for i in range(1, 6)]
        page, next_cursor = paginate(items, sort_key=_sort_key, cursor=None, limit=2)
        assert [i[1] for i in page] == [1, 2]
        assert next_cursor is not None

    def test_cursor_resumes_after_the_last_seen_item(self) -> None:
        items = [("2026-01-0" + str(i), i) for i in range(1, 6)]
        _first_page, cursor = paginate(items, sort_key=_sort_key, cursor=None, limit=2)
        second_page, _ = paginate(items, sort_key=_sort_key, cursor=cursor, limit=2)
        assert [i[1] for i in second_page] == [3, 4]

    def test_last_page_has_no_next_cursor(self) -> None:
        items = [("2026-01-01", 1), ("2026-01-02", 2)]
        page, next_cursor = paginate(items, sort_key=_sort_key, cursor=None, limit=10)
        assert len(page) == 2
        assert next_cursor is None

    def test_empty_input_returns_empty_page(self) -> None:
        items: list[tuple[str, int]] = []
        page, next_cursor = paginate(items, sort_key=_sort_key, cursor=None, limit=10)
        assert page == []
        assert next_cursor is None
