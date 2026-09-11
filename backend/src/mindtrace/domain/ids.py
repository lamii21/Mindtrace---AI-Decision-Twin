"""Typed identifiers for the schema vocabulary.

``NewType`` aliases: zero runtime cost, but mypy rejects passing a bare ``str``
where a ``FactorId`` is expected, so identifier spaces cannot be crossed by
accident (e.g. a disposition id used as a factor key). Format validation
(snake-case shape) lives in the JSON Schemas (``schema/*.schema.json``), which
every ``load_*`` entry point checks before these types are ever constructed.

Entity identifiers (``UserId``, ``MemoryId``, ...) are introduced in the
milestone that first persists those entities (M4+); nothing in M1 needs them.
"""

from __future__ import annotations

from typing import NewType

FactorId = NewType("FactorId", str)
DispositionId = NewType("DispositionId", str)
InterviewItemId = NewType("InterviewItemId", str)
EvidenceTag = NewType("EvidenceTag", str)
