"""Tests for the event vocabulary and record type (``mindtrace.events.types``)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from mindtrace.domain.enums import MemoryType, ProvenanceSource
from mindtrace.domain.errors import DomainError
from mindtrace.domain.ids import EventId, InterviewItemId, MemoryId, UserId
from mindtrace.events.enums import MemoryEventType
from mindtrace.events.types import (
    CorrectedPayload,
    DeletedPayload,
    ElicitationAnsweredPayload,
    Event,
    IngestedPayload,
)


def _make_event(**overrides: object) -> Event:
    defaults: dict[str, object] = {
        "id": EventId(uuid4()),
        "user_id": UserId(uuid4()),
        "seq": 1,
        "type": MemoryEventType.INGESTED,
        "payload": {"content": "hello", "memory_type": "episodic"},
        "source": ProvenanceSource.DECLARED,
        "occurred_at": None,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    defaults.update(overrides)
    return Event.model_validate(defaults)


class TestMemoryEventType:
    def test_has_exactly_the_five_approved_values(self) -> None:
        assert {m.value for m in MemoryEventType} == {
            "ingested",
            "corrected",
            "deleted",
            "elicitation_answered",
            "outcome_recorded",
        }


class TestPayloads:
    def test_ingested_payload_event_type_classvar(self) -> None:
        assert IngestedPayload.event_type is MemoryEventType.INGESTED

    def test_corrected_payload_event_type_classvar(self) -> None:
        assert CorrectedPayload.event_type is MemoryEventType.CORRECTED

    def test_deleted_payload_event_type_classvar(self) -> None:
        assert DeletedPayload.event_type is MemoryEventType.DELETED

    def test_ingested_payload_rejects_empty_content(self) -> None:
        with pytest.raises(ValidationError):
            IngestedPayload(content="", memory_type=MemoryType.EPISODIC)

    def test_corrected_payload_rejects_empty_content(self) -> None:
        with pytest.raises(ValidationError):
            CorrectedPayload(target_memory_id=MemoryId(uuid4()), content="")

    def test_deleted_payload_rejects_empty_target_list(self) -> None:
        with pytest.raises(ValidationError):
            DeletedPayload(target_memory_ids=())

    def test_payloads_are_frozen(self) -> None:
        payload = IngestedPayload(content="x", memory_type=MemoryType.EPISODIC)
        with pytest.raises(ValidationError):
            payload.content = "y"

    def test_payloads_reject_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            IngestedPayload(content="x", memory_type=MemoryType.EPISODIC, extra_field=1)  # type: ignore[call-arg]


class TestElicitationAnsweredPayload:
    def test_event_type_classvar(self) -> None:
        assert ElicitationAnsweredPayload.event_type is MemoryEventType.ELICITATION_ANSWERED

    def test_accepts_a_b_and_indifferent_choices(self) -> None:
        for choice in ("A", "B", "indifferent"):
            payload = ElicitationAnsweredPayload(item_id=InterviewItemId("p01"), choice=choice)
            assert payload.choice == choice

    def test_rejects_an_invalid_choice(self) -> None:
        with pytest.raises(ValidationError):
            ElicitationAnsweredPayload(item_id=InterviewItemId("p01"), choice="C")  # type: ignore[arg-type]

    def test_latency_ms_is_optional(self) -> None:
        payload = ElicitationAnsweredPayload(item_id=InterviewItemId("p01"), choice="A")
        assert payload.latency_ms is None

    def test_is_frozen(self) -> None:
        payload = ElicitationAnsweredPayload(item_id=InterviewItemId("p01"), choice="A")
        with pytest.raises(ValidationError):
            payload.choice = "B"

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            ElicitationAnsweredPayload(item_id=InterviewItemId("p01"), choice="A", bogus=1)  # type: ignore[call-arg]


class TestEvent:
    def test_is_frozen(self) -> None:
        event = _make_event()
        with pytest.raises(ValidationError):
            event.seq = 2

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            _make_event(not_a_real_field=1)

    def test_causation_and_correlation_ids_default_to_none(self) -> None:
        event = _make_event()
        assert event.causation_id is None
        assert event.correlation_id is None

    def test_serialisation_round_trip_preserves_every_field(self) -> None:
        event = _make_event(causation_id=EventId(uuid4()), correlation_id=uuid4())
        restored = Event.model_validate(event.model_dump(mode="json"))
        assert restored == event

    @pytest.mark.parametrize(
        ("event_type", "payload", "expected_model"),
        [
            (
                MemoryEventType.INGESTED,
                {"content": "hi", "memory_type": "episodic"},
                IngestedPayload,
            ),
            (
                MemoryEventType.CORRECTED,
                {"target_memory_id": str(uuid4()), "content": "hi"},
                CorrectedPayload,
            ),
            (
                MemoryEventType.DELETED,
                {"target_memory_ids": [str(uuid4())]},
                DeletedPayload,
            ),
            (
                MemoryEventType.ELICITATION_ANSWERED,
                {"item_id": "p01", "choice": "A"},
                ElicitationAnsweredPayload,
            ),
        ],
    )
    def test_typed_payload_parses_the_matching_model(
        self, event_type: MemoryEventType, payload: dict[str, object], expected_model: type
    ) -> None:
        event = _make_event(type=event_type, payload=payload)
        assert isinstance(event.typed_payload(), expected_model)

    @pytest.mark.parametrize("event_type", [MemoryEventType.OUTCOME_RECORDED])
    def test_typed_payload_raises_for_unmodelled_types(self, event_type: MemoryEventType) -> None:
        """``elicitation_answered`` now has a typed payload - see
        ``TestElicitationAnsweredPayload``.
        """
        event = _make_event(type=event_type, payload={})
        with pytest.raises(DomainError, match="no typed payload model"):
            event.typed_payload()

    def test_typed_payload_raises_on_malformed_payload_for_its_own_type(self) -> None:
        # missing memory_type
        event = _make_event(type=MemoryEventType.INGESTED, payload={"content": "hi"})
        with pytest.raises(ValidationError):
            event.typed_payload()
