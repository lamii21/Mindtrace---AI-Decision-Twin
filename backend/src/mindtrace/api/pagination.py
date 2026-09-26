"""Opaque cursor pagination (``docs/api/08`` s1: "Opaque `cursor` + `limit`").

In-memory slicing over an already-fetched, sorted sequence - correct and
simple at this project's documented realistic per-user scale (ADR-001:
O(10^4) events for a heavy user), not a streaming/keyset-scan
implementation. The cursor itself is opaque to the client (a base64 blob),
so this can be swapped for a real keyset-scan later without changing the
wire contract.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Sequence

DEFAULT_LIMIT = 25
MAX_LIMIT = 100


def encode_cursor(sort_key: tuple[str, str]) -> str:
    """Encode the last-seen item's sort key into an opaque cursor string."""
    return base64.urlsafe_b64encode(json.dumps(list(sort_key)).encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    decoded = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
    return decoded[0], decoded[1]


def paginate[T](
    items: Sequence[T],
    *,
    sort_key: Callable[[T], tuple[str, str]],
    cursor: str | None,
    limit: int,
) -> tuple[list[T], str | None]:
    """Sort ``items`` by ``sort_key`` and return the page after ``cursor``.

    Returns ``(page, next_cursor)`` - ``next_cursor`` is ``None`` once the
    last page is reached.
    """
    ordered = sorted(items, key=sort_key)
    start = 0
    if cursor is not None:
        after = _decode_cursor(cursor)
        for index, item in enumerate(ordered):
            if sort_key(item) > after:
                start = index
                break
        else:
            start = len(ordered)
    page = ordered[start : start + limit]
    has_more = start + limit < len(ordered) and bool(page)
    next_cursor = encode_cursor(sort_key(page[-1])) if has_more else None
    return page, next_cursor
