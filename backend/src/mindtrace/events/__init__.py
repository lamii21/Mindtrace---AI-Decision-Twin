"""MINDTRACE event-sourcing layer.

Layer 1 of the architecture (``docs/architecture/01-repository-structure.md``):
event types, the append-only store port (+ an in-memory implementation),
projectors, and re-derivation. Depends only on ``mindtrace.domain`` and the
standard library -- never ``fastapi``, ``sqlalchemy``, an LLM provider SDK, or
any higher ``mindtrace`` layer -- enforced by ``backend/.importlinter`` and
``tests/unit/test_import_isolation.py``.
"""

from __future__ import annotations

from mindtrace.events.enums import MemoryEventType
from mindtrace.events.evidence_store import EvidenceStore, InMemoryEvidenceStore
from mindtrace.events.in_memory_store import InMemoryEventStore
from mindtrace.events.projectors.memory import (
    MEMORY_PROJECTOR_VERSION,
    MemoryProjectionState,
    fold_memory_events,
)
from mindtrace.events.rederive import DeletionImpact, apply_deletion, preview_deletion, rederive
from mindtrace.events.store import EventStore
from mindtrace.events.types import (
    CorrectedPayload,
    DeletedPayload,
    Event,
    EventPayload,
    IngestedPayload,
)

__all__ = [
    "MEMORY_PROJECTOR_VERSION",
    "CorrectedPayload",
    "DeletedPayload",
    "DeletionImpact",
    "Event",
    "EventPayload",
    "EventStore",
    "EvidenceStore",
    "InMemoryEventStore",
    "InMemoryEvidenceStore",
    "IngestedPayload",
    "MemoryEventType",
    "MemoryProjectionState",
    "apply_deletion",
    "fold_memory_events",
    "preview_deletion",
    "rederive",
]
