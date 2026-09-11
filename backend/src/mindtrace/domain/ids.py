"""Typed identifiers.

Two families, both ``NewType`` aliases (zero runtime cost, but mypy rejects
passing a bare ``str``/``UUID`` where a specific id type is expected, so
identifier spaces cannot be crossed by accident):

- **Schema vocabulary ids** (``FactorId``, ``DispositionId``, ...) - plain
  strings. Format validation (snake-case shape) lives in the JSON Schemas
  (``schema/*.schema.json``), which every ``load_*`` entry point checks before
  these types are ever constructed.
- **Entity ids** (``UserId``, ``MemoryId``, ...) - UUIDs, introduced in M2 for
  the event-sourced memory/evidence foundation. Belief-side ids
  (``Evidence.belief_id``) stay a bare ``UUID`` rather than a typed alias:
  M2 has no belief-producing engine yet (ADR-001/M2), so there is no concrete
  id space to name.
"""

from __future__ import annotations

from typing import NewType
from uuid import UUID

FactorId = NewType("FactorId", str)
DispositionId = NewType("DispositionId", str)
InterviewItemId = NewType("InterviewItemId", str)
EvidenceTag = NewType("EvidenceTag", str)

UserId = NewType("UserId", UUID)
EventId = NewType("EventId", UUID)
MemoryId = NewType("MemoryId", UUID)
EvidenceId = NewType("EvidenceId", UUID)
