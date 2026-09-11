"""Tests for rebuild-from-history and deletion preview/apply (``mindtrace.events.rederive``)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from mindtrace.domain.enums import BeliefType, EvidenceSourceKind, Polarity, ProvenanceSource
from mindtrace.domain.errors import DomainError
from mindtrace.domain.evidence import Evidence
from mindtrace.domain.ids import EvidenceId, MemoryId, UserId
from mindtrace.events.evidence_store import InMemoryEvidenceStore
from mindtrace.events.projectors.memory import fold_memory_events
from mindtrace.events.rederive import apply_deletion, preview_deletion, rederive
from tests.support.memory_fixtures import (
    FIXED_NOW,
    FIXED_USER,
    correct,
    deterministic_store,
    ingest,
)


class TestRederive:
    def test_matches_a_manual_fold_of_the_same_stream(self) -> None:
        store = deterministic_store()
        ingest(store, content="a")
        ingest(store, content="b")
        first_id = MemoryId(store.read_stream(FIXED_USER)[0].id)
        correct(store, target=first_id, content="a-corrected")

        expected = fold_memory_events(FIXED_USER, store.read_stream(FIXED_USER))
        assert rederive(store, FIXED_USER) == expected

    def test_rederiving_twice_in_a_row_is_equal(self) -> None:
        store = deterministic_store()
        ingest(store, content="a")
        assert rederive(store, FIXED_USER) == rederive(store, FIXED_USER)

    def test_reflects_events_appended_after_a_prior_rederive(self) -> None:
        store = deterministic_store()
        ingest(store, content="a")
        first = rederive(store, FIXED_USER)
        assert len(first.memories) == 1

        ingest(store, content="b")
        second = rederive(store, FIXED_USER)
        assert len(second.memories) == 2
        # the first memory is still present and unchanged by the later append
        assert first.memories.keys() <= second.memories.keys()

    def test_unknown_user_rederives_to_an_empty_state(self) -> None:
        store = deterministic_store()
        state = rederive(store, UserId(uuid4()))
        assert state.memories == {}
        assert state.last_seq == 0


def _record_evidence(evidence_store: InMemoryEvidenceStore, *, source_id: MemoryId) -> Evidence:
    return evidence_store.record(
        Evidence(
            id=EvidenceId(uuid4()),
            user_id=FIXED_USER,
            belief_type=BeliefType.DECISION_FACTOR,
            belief_id=uuid4(),
            source_kind=EvidenceSourceKind.MEMORY,
            source_id=source_id,
            weight=1.0,
            polarity=Polarity.SUPPORT,
            engine_version="test",
            created_at=FIXED_NOW,
        )
    )


class TestPreviewDeletion:
    def test_reports_affected_evidence(self) -> None:
        store = deterministic_store()
        event = ingest(store, content="I rejected the offer over the commute.")
        state = rederive(store, FIXED_USER)
        memory_id = MemoryId(event.id)

        evidence_store = InMemoryEvidenceStore()
        evidence = _record_evidence(evidence_store, source_id=memory_id)

        impact = preview_deletion(state, (memory_id,), evidence_store=evidence_store)
        assert impact.memory_ids == (memory_id,)
        assert impact.affected_evidence == (evidence,)

    def test_memory_with_no_evidence_has_empty_impact(self) -> None:
        store = deterministic_store()
        event = ingest(store, content="no evidence points at this")
        state = rederive(store, FIXED_USER)
        impact = preview_deletion(
            state, (MemoryId(event.id),), evidence_store=InMemoryEvidenceStore()
        )
        assert impact.affected_evidence == ()

    def test_unknown_memory_id_raises_key_error(self) -> None:
        store = deterministic_store()
        ingest(store, content="a")
        state = rederive(store, FIXED_USER)
        with pytest.raises(KeyError):
            preview_deletion(state, (MemoryId(uuid4()),), evidence_store=InMemoryEvidenceStore())

    def test_already_deleted_memory_raises(self) -> None:
        store = deterministic_store()
        event = ingest(store, content="a")
        state = rederive(store, FIXED_USER)
        memory_id = MemoryId(event.id)
        evidence_store = InMemoryEvidenceStore()

        _impact, state_after = apply_deletion(
            store,
            state,
            (memory_id,),
            evidence_store=evidence_store,
            source=ProvenanceSource.DECLARED,
            now=FIXED_NOW,
        )
        with pytest.raises(DomainError, match="already deleted"):
            preview_deletion(state_after, (memory_id,), evidence_store=evidence_store)


class TestApplyDeletion:
    def test_actually_tombstones_and_returns_the_preview(self) -> None:
        store = deterministic_store()
        event = ingest(store, content="forget me")
        state = rederive(store, FIXED_USER)
        memory_id = MemoryId(event.id)
        evidence_store = InMemoryEvidenceStore()

        impact, new_state = apply_deletion(
            store,
            state,
            (memory_id,),
            evidence_store=evidence_store,
            source=ProvenanceSource.DECLARED,
            now=FIXED_NOW,
        )

        assert impact.memory_ids == (memory_id,)
        assert new_state.get(memory_id).deleted_at is not None
        assert new_state.get(memory_id) not in new_state.active_memories

    def test_result_matches_a_fresh_rederive(self) -> None:
        store = deterministic_store()
        event = ingest(store, content="forget me too")
        state = rederive(store, FIXED_USER)
        memory_id = MemoryId(event.id)

        _impact, new_state = apply_deletion(
            store,
            state,
            (memory_id,),
            evidence_store=InMemoryEvidenceStore(),
            source=ProvenanceSource.DECLARED,
            now=FIXED_NOW,
        )

        assert new_state == rederive(store, FIXED_USER)
