"""The memory projection: what MINDTRACE currently believes it was told.

``Memory`` is a tier-C projection (``docs/architecture/02-domain-model.md`` s1):
folded from the append-only event log (``mindtrace.events``), never authored
directly. This module defines only the *shape*; folding events into it is
``mindtrace.events.projectors.memory``.

Trimmed from the domain-model doc's full AG-3 sketch on purpose: ``confidence``,
``salience``, and ``embedding`` all require an engine that does not exist yet
(confidence model M3/M6, embeddings M5) and are deliberately omitted rather
than populated with a placeholder value that would look computed but isn't
(principle 15/M2 s18). ``Experience`` (the episodic subtype with
role/org/period fields) is likewise deferred - nothing in M2 needs it, and
adding it now would be a speculative field (M2 s9).
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from mindtrace.domain.enums import MemoryType, ProvenanceSource
from mindtrace.domain.ids import MemoryId, UserId

_FrozenModel = ConfigDict(frozen=True, extra="forbid")


class Memory(BaseModel):
    """One thing MINDTRACE currently believes it was told, and where that came from.

    Answers, without an LLM (M2 s9): what (``content``), whose (``user_id``),
    when (``occurred_at``), how it's known (``source``), which event
    established it (``origin_event_seq``), and which event superseded or
    deleted it, if any (``superseded_by`` / ``deleted_at`` +
    ``deleted_by_event_seq``). "Which evidence supports it" and "what is its
    epistemic state" are deliberately *not* stored fields - they are answered
    by querying :class:`~mindtrace.events.evidence_store.EvidenceStore` and by
    :func:`mindtrace.domain.provenance.classify_epistemic_state` respectively,
    so there is nothing here that can drift out of sync with its source of
    truth.
    """

    model_config = _FrozenModel

    id: MemoryId
    user_id: UserId
    type: MemoryType
    content: str
    source: ProvenanceSource
    occurred_at: date | None
    origin_event_seq: int
    superseded_by: MemoryId | None = None
    deleted_at: datetime | None = None
    deleted_by_event_seq: int | None = None
    projector_version: str

    @property
    def is_current(self) -> bool:
        """False once superseded by a correction or removed by a deletion."""
        return self.superseded_by is None and self.deleted_at is None
