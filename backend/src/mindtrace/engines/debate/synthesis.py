"""The ensemble's final recommendation: a weight-of-evidence vote (ADR-007, M10).

The base twin's vote counts double; every other twin counts once. Purely a
tally over each twin's own already-computed ``DecisionResult.label`` - never
a re-run of MCDA, never an LLM judgement.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from mindtrace.domain.enums import DecisionOutcome
from mindtrace.domain.simulation import SynthesisResult, TwinConfigResult
from mindtrace.domain.twins import BASE_TWIN_ID
from mindtrace.engines.debate.disagreement import conflict_axis, label_consensus

SYNTHESIS_VERSION = "1"

#: The base twin's vote counts double (ADR-007: "a weight-of-evidence vote
#: (base twin counts double)") - it is the user's own, untransformed
#: preference, so it anchors the recommendation more than any single shifted
#: variant.
BASE_TWIN_VOTE_WEIGHT = 2.0
_OTHER_TWIN_VOTE_WEIGHT = 1.0


def synthesize(
    twin_results: Sequence[TwinConfigResult], *, base_twin_id: str = BASE_TWIN_ID
) -> SynthesisResult:
    """Tally the twins' labels into one recommendation, plus consensus/conflict-axis diagnostics.

    Raises:
        ValueError: ``twin_results`` is empty, or does not contain exactly
            one twin named ``base_twin_id``.
    """
    if not twin_results:
        msg = "synthesize requires at least one twin result"
        raise ValueError(msg)
    base_count = sum(1 for r in twin_results if r.twin == base_twin_id)
    if base_count != 1:
        msg = f"expected exactly one twin named {base_twin_id!r}, found {base_count}"
        raise ValueError(msg)

    votes: dict[DecisionOutcome, float] = defaultdict(float)
    for result in twin_results:
        weight = BASE_TWIN_VOTE_WEIGHT if result.twin == base_twin_id else _OTHER_TWIN_VOTE_WEIGHT
        votes[result.decision.label] += weight

    total_votes = sum(votes.values())
    ranked = sorted(votes.items(), key=lambda item: (-item[1], item[0].value))
    winner_label, winner_votes = ranked[0]
    runner_up_votes = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = (winner_votes - runner_up_votes) / total_votes

    return SynthesisResult(
        recommended_label=winner_label,
        margin=margin,
        vote_tally={label.value: weight for label, weight in votes.items()},
        label_consensus=label_consensus([r.decision.label for r in twin_results]),
        conflict_axis=conflict_axis(twin_results),
        synthesis_version=SYNTHESIS_VERSION,
    )


__all__ = ["BASE_TWIN_VOTE_WEIGHT", "SYNTHESIS_VERSION", "synthesize"]
