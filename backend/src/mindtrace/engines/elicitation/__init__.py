"""The fixed-order Twin Interview engine (M8; spec/07, roadmap "Twin Interview (fixed order)").

Pure: item ordering (``select_fixed``), session progress (``session``),
finalisation into a ``PreferencePosterior`` (``finalize``), and turning a
belief dispute into one more batch update (``dispute``, M9) - no
persistence, no HTTP, no clock reads. Active Elicitation
(expected-information-gain adaptive selection) is out of scope for this
milestone; spec/07 §5 already specifies that math for whichever later
milestone implements it.
"""

from __future__ import annotations

from mindtrace.engines.elicitation.dispute import (
    DISPUTE_REPEAT_COUNT,
    DISPUTE_VERSION,
    apply_dispute,
)
from mindtrace.engines.elicitation.finalize import (
    FINALIZE_VERSION,
    compute_interview_noise,
    consistency_pairs,
    finalize_interview,
)
from mindtrace.engines.elicitation.select_fixed import (
    FIXED_ORDER_VERSION,
    FIXED_SUFFIX_ORDER,
    fixed_prefix_order,
    full_fixed_order,
    next_item_id,
)
from mindtrace.engines.elicitation.session import InterviewProgress, is_complete, progress_for

__all__ = [
    "DISPUTE_REPEAT_COUNT",
    "DISPUTE_VERSION",
    "FINALIZE_VERSION",
    "FIXED_ORDER_VERSION",
    "FIXED_SUFFIX_ORDER",
    "InterviewProgress",
    "apply_dispute",
    "compute_interview_noise",
    "consistency_pairs",
    "finalize_interview",
    "fixed_prefix_order",
    "full_fixed_order",
    "is_complete",
    "next_item_id",
    "progress_for",
]
