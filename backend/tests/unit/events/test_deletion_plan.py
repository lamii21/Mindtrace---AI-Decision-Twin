"""Tests for classifying a ``DeletionImpact`` into belief-level facts (M9)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from mindtrace.domain.enums import BeliefType, EvidenceSourceKind, Polarity
from mindtrace.domain.evidence import Evidence
from mindtrace.domain.ids import EvidenceId, MemoryId, UserId
from mindtrace.events.deletion_plan import build_deletion_plan_facts
from mindtrace.events.rederive import DeletionImpact

_FIXED_USER = UserId(uuid4())
_FIXED_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _evidence(
    *, belief_type: BeliefType, belief_id: UUID, source_kind: EvidenceSourceKind
) -> Evidence:
    return Evidence(
        id=EvidenceId(uuid4()),
        user_id=_FIXED_USER,
        belief_type=belief_type,
        belief_id=belief_id,
        source_kind=source_kind,
        source_id=uuid4(),
        weight=1.0,
        polarity=Polarity.SUPPORT,
        engine_version="1",
        created_at=_FIXED_NOW,
    )


def _impact(*evidence: Evidence) -> DeletionImpact:
    return DeletionImpact(memory_ids=(MemoryId(uuid4()),), affected_evidence=evidence)


class TestBuildDeletionPlanFacts:
    def test_no_affected_evidence_gives_an_empty_honest_plan(self) -> None:
        facts = build_deletion_plan_facts(_impact())
        assert facts.affected_beliefs == ()
        assert facts.twin_version_will_bump is False

    def test_a_preference_belief_sets_twin_version_will_bump(self) -> None:
        belief_id = uuid4()
        evidence = _evidence(
            belief_type=BeliefType.PREFERENCE,
            belief_id=belief_id,
            source_kind=EvidenceSourceKind.MEMORY,
        )
        facts = build_deletion_plan_facts(_impact(evidence))
        assert len(facts.affected_beliefs) == 1
        assert facts.affected_beliefs[0].belief_type is BeliefType.PREFERENCE
        assert facts.affected_beliefs[0].belief_id == belief_id
        assert facts.affected_beliefs[0].change == "recompute"
        assert facts.twin_version_will_bump is True

    def test_a_trait_belief_also_sets_twin_version_will_bump(self) -> None:
        evidence = _evidence(
            belief_type=BeliefType.TRAIT, belief_id=uuid4(), source_kind=EvidenceSourceKind.MEMORY
        )
        facts = build_deletion_plan_facts(_impact(evidence))
        assert facts.twin_version_will_bump is True

    def test_a_decision_factor_belief_does_not_set_twin_version_will_bump(self) -> None:
        evidence = _evidence(
            belief_type=BeliefType.DECISION_FACTOR,
            belief_id=uuid4(),
            source_kind=EvidenceSourceKind.MEMORY,
        )
        facts = build_deletion_plan_facts(_impact(evidence))
        assert len(facts.affected_beliefs) == 1
        assert facts.twin_version_will_bump is False

    def test_repeated_edges_to_the_same_belief_are_deduplicated(self) -> None:
        belief_id = uuid4()
        edge_a = _evidence(
            belief_type=BeliefType.PREFERENCE,
            belief_id=belief_id,
            source_kind=EvidenceSourceKind.MEMORY,
        )
        edge_b = _evidence(
            belief_type=BeliefType.PREFERENCE,
            belief_id=belief_id,
            source_kind=EvidenceSourceKind.MEMORY,
        )
        facts = build_deletion_plan_facts(_impact(edge_a, edge_b))
        assert len(facts.affected_beliefs) == 1

    def test_distinct_beliefs_are_both_reported(self) -> None:
        pref = _evidence(
            belief_type=BeliefType.PREFERENCE,
            belief_id=uuid4(),
            source_kind=EvidenceSourceKind.MEMORY,
        )
        decision = _evidence(
            belief_type=BeliefType.DECISION_FACTOR,
            belief_id=uuid4(),
            source_kind=EvidenceSourceKind.MEMORY,
        )
        facts = build_deletion_plan_facts(_impact(pref, decision))
        assert len(facts.affected_beliefs) == 2
        assert facts.twin_version_will_bump is True
