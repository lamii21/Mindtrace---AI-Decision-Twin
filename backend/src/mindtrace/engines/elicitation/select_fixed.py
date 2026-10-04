"""Deterministic fixed-order item selection for the v1 Twin Interview (spec/07 §2).

Roadmap M8 is titled "Twin Interview (fixed order)"; spec/07 §2 itself names
the fixed suffix as "the first shippable version" ("the adaptive selector is
a fast-follow"). No expected-information-gain computation happens anywhere
in this module or milestone - spec/07 §5 already fully specifies that math
for whichever later milestone implements it (M8 planning s8/s21).

v1 does not implement the Likert warm-up (spec/07 §2 step 1): no
``LikertItem`` domain type exists yet (``domain/interview.py`` models only
``pairwise``/``disposition`` items), and the roadmap's own M8 objective line
does not name it. The fixed prefix (12 items) + fixed suffix (10 items) = 22
answers already lands inside ``interview.yaml``'s own ``target_total=[18,24]``
without it - a reported, narrow scope trim, not a silent omission (M8
planning s21/final report).
"""

from __future__ import annotations

from mindtrace.domain.enums import InterviewItemRole
from mindtrace.domain.ids import InterviewItemId
from mindtrace.domain.interview import InterviewBank

FIXED_ORDER_VERSION = "1"

# The fixed suffix after the 12-item prefix: spec/07 §2's own partial example
# ("d01,d03,d05,d07,p03r,p07r,d02,d04,...") completed to its full 10-item
# length by extending the stated pattern - one item of each disposition type,
# then both consistency checks, then each type's second item (approved
# resolution, M8 planning s21/s23 - the user's own report-approval).
FIXED_SUFFIX_ORDER: tuple[InterviewItemId, ...] = tuple(
    InterviewItemId(i)
    for i in ("d01", "d03", "d05", "d07", "p03r", "p07r", "d02", "d04", "d06", "d08")
)


def fixed_prefix_order(bank: InterviewBank) -> tuple[InterviewItemId, ...]:
    """The standard (non-consistency-check) pairwise items, in bank file order.

    The real bank has 14 such items (p01-p14), not the 12
    ``interview.yaml config.fixed_prefix_items`` names - that constant is
    not cross-checked against the actual item composition anywhere in
    ``domain/interview.py``'s loader (it only checks
    ``fixed_prefix_items <= total``), and asking every item in the bank
    (14 prefix + the approved 10-item suffix = 24) lands exactly at
    ``target_total_max=24``, the cleanest self-consistent reading. Treated
    as a stale/documentation-only config value, not a binding exclusion
    rule (M8 planning s21, reported as a non-blocking deviation).
    """
    return tuple(item.id for item in bank.pairwise if item.role is InterviewItemRole.STANDARD)


def full_fixed_order(bank: InterviewBank) -> tuple[InterviewItemId, ...]:
    """The complete v1 fixed item order: prefix, then suffix.

    Raises:
        ValueError: ``FIXED_SUFFIX_ORDER`` does not exactly match
            ``bank``'s disposition items + consistency-check pairwise items
            (a bank-version mismatch) - caught at the boundary rather than
            silently asking fewer/wrong items.
    """
    prefix = fixed_prefix_order(bank)
    order = prefix + FIXED_SUFFIX_ORDER
    if frozenset(order) != frozenset(bank.item_ids):
        msg = (
            "FIXED_SUFFIX_ORDER does not exactly cover this bank's items - "
            f"missing {frozenset(bank.item_ids) - frozenset(order)}, "
            f"unexpected {frozenset(order) - frozenset(bank.item_ids)}"
        )
        raise ValueError(msg)
    return order


def next_item_id(
    bank: InterviewBank, answered_item_ids: frozenset[InterviewItemId]
) -> InterviewItemId | None:
    """The next unanswered item in the fixed order, or ``None`` once every item is answered."""
    for item_id in full_fixed_order(bank):
        if item_id not in answered_item_ids:
            return item_id
    return None


__all__ = [
    "FIXED_ORDER_VERSION",
    "FIXED_SUFFIX_ORDER",
    "fixed_prefix_order",
    "full_fixed_order",
    "next_item_id",
]
