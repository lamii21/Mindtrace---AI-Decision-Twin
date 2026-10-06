"""Turning a belief dispute into one M4 batch update (M9; spec/07 §4.1/§4.2 reused verbatim).

A dispute is mechanically "answer one interview item again, with more
emphasis" - never a new observation-from-scalar formula. ``PairwiseObservation.
weight`` is bounded to ``(0, 1]`` by its own validator (spec/04 §3) and
``DispositionObservation`` carries no weight field at all, so "more emphasis"
cannot mean a larger per-observation weight without changing M4's domain
contract. Instead, exactly like ``tests/golden/test_preference_golden.py``'s
own ``TestRepeatedObservation`` ("the same observation five times: further
and narrower than once" - an already-tested M4 behaviour), a dispute submits
the *same* observation :data:`DISPUTE_REPEAT_COUNT` times in one batch. Zero
new mathematics; only a named, versioned repeat count.
"""

from __future__ import annotations

from mindtrace.domain.enums import ChoiceOption
from mindtrace.domain.factors import FactorTaxonomy
from mindtrace.domain.interview import DispositionItem, PairwiseItem
from mindtrace.domain.traits import PreferencePosterior
from mindtrace.engines.preference.config import PreferenceConfig
from mindtrace.engines.preference.interview import (
    disposition_observation_from_item,
    pairwise_observation_from_item,
)
from mindtrace.engines.preference.update import (
    apply_disposition_observations,
    apply_pairwise_observations,
)

DISPUTE_VERSION = "1"

# Chosen so one dispute measurably outmoves a single ordinary interview
# answer (sigma shrinks further, mu moves further - see
# `TestRepeatedObservation`) without being able to swamp all 24 fixed-order
# answers on its own (the interview's own batch already outnumbers it 24:5).
# A tunable constant, not a formula - revisit only with a deliberate,
# reviewed change (M9 planning).
DISPUTE_REPEAT_COUNT = 5


def apply_dispute(
    item: PairwiseItem | DispositionItem,
    choice: ChoiceOption | None,
    prior: PreferencePosterior,
    *,
    taxonomy: FactorTaxonomy,
    config: PreferenceConfig,
) -> PreferencePosterior:
    """Run one batch update of :data:`DISPUTE_REPEAT_COUNT` copies of ``item``'s observation.

    Calls M4's ``apply_pairwise_observations``/``apply_disposition_observations``
    exactly once - never incrementally - exactly like
    ``engines.elicitation.finalize``'s own batch-update discipline.
    """
    if isinstance(item, PairwiseItem):
        pairwise_observation = pairwise_observation_from_item(item, choice, taxonomy)
        return apply_pairwise_observations(
            prior, [pairwise_observation] * DISPUTE_REPEAT_COUNT, config
        )
    disposition_observation = disposition_observation_from_item(item, choice)
    return apply_disposition_observations(
        prior, [disposition_observation] * DISPUTE_REPEAT_COUNT, config
    )


__all__ = ["DISPUTE_REPEAT_COUNT", "DISPUTE_VERSION", "apply_dispute"]
