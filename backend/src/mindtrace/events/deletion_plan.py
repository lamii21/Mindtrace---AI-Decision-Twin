"""Classifying a :class:`~mindtrace.events.rederive.DeletionImpact` into belief-level facts (M9).

Pure: no DB, no API schema. ``rederive.py`` (M2) already computes *which*
``Evidence`` edges a deletion touches - this module only groups that into
"which beliefs, and does this look recompute-worthy" facts, the shape
``services/memory_service.py`` hands to the API's ``DeletionPlan`` DTO.
Counting invalidated ``Prediction``s needs a repository lookup (DB), so it
stays out of this module and is the service layer's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from mindtrace.domain.enums import BeliefType
from mindtrace.events.rederive import DeletionImpact

DELETION_PLAN_VERSION = "1"


@dataclass(frozen=True)
class BeliefImpactFact:
    """One belief a deletion would affect - before any DTO/API shaping."""

    belief_type: BeliefType
    belief_id: UUID
    change: str  # "recompute" - M9 never computes "remove" (would need full re-derivation)


@dataclass(frozen=True)
class DeletionPlanFacts:
    """Everything a ``DeletionPlan`` response needs that is derivable from ``Evidence`` alone."""

    affected_beliefs: tuple[BeliefImpactFact, ...]
    twin_version_will_bump: bool


# Belief types the preference engine (M4/M8) can recompute from evidence -
# a deletion touching one of these is the only case `twin_version_will_bump`
# can honestly report `True` for; `decision_factor`/`value`/`contradiction`
# recompute through different (not-yet-wired) paths.
_PREFERENCE_RECOMPUTABLE: frozenset[BeliefType] = frozenset(
    {BeliefType.PREFERENCE, BeliefType.TRAIT}
)


def build_deletion_plan_facts(impact: DeletionImpact) -> DeletionPlanFacts:
    """Group ``impact.affected_evidence`` by belief, deduplicating repeated edges to one belief.

    Every real producer today writes Evidence at a coarse grain (one edge
    per ``TwinVersion``/``Simulation``, not per factor) - this function does
    not assume otherwise; it only reports what the edges actually name.
    """
    seen: dict[tuple[BeliefType, UUID], BeliefImpactFact] = {}
    for evidence in impact.affected_evidence:
        key = (evidence.belief_type, evidence.belief_id)
        if key not in seen:
            seen[key] = BeliefImpactFact(
                belief_type=evidence.belief_type, belief_id=evidence.belief_id, change="recompute"
            )

    affected_beliefs = tuple(seen.values())
    will_bump = any(fact.belief_type in _PREFERENCE_RECOMPUTABLE for fact in affected_beliefs)
    return DeletionPlanFacts(affected_beliefs=affected_beliefs, twin_version_will_bump=will_bump)


__all__ = [
    "DELETION_PLAN_VERSION",
    "BeliefImpactFact",
    "DeletionPlanFacts",
    "build_deletion_plan_facts",
]
