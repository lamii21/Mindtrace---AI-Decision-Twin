"""Pure Twin Interview session-progress computations (no I/O, no persistence).

Progress is always derived from the fixed order (``select_fixed.py``) plus
the set of already-answered item ids - never stored as its own mutable
counter, so it can never drift from what the answer log actually says.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from mindtrace.domain.ids import InterviewItemId
from mindtrace.domain.interview import InterviewBank
from mindtrace.engines.elicitation.select_fixed import full_fixed_order, next_item_id

_FrozenModel = ConfigDict(frozen=True, extra="forbid")


class InterviewProgress(BaseModel):
    """How far through the fixed order a session has gotten."""

    model_config = _FrozenModel

    answered: int = Field(ge=0)
    target: int = Field(ge=0)


def progress_for(
    bank: InterviewBank, answered_item_ids: frozenset[InterviewItemId]
) -> InterviewProgress:
    """``answered`` among the items actually in the fixed order; ``target`` is its full length."""
    order = frozenset(full_fixed_order(bank))
    return InterviewProgress(answered=len(answered_item_ids & order), target=len(order))


def is_complete(bank: InterviewBank, answered_item_ids: frozenset[InterviewItemId]) -> bool:
    """Every fixed-order item has an answer (v1: no early stopping - see ``select_fixed``)."""
    return next_item_id(bank, answered_item_ids) is None


__all__ = ["InterviewProgress", "is_complete", "progress_for"]
