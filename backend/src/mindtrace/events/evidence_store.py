"""The evidence store port and its in-memory implementation.

``Evidence`` is tier B (``docs/architecture/02-domain-model.md`` s1):
immutable once written, but - unlike ``Memory`` - not folded from the event
log. A future engine writes it directly as a side effect of deriving a
belief. This store is the append-only home for those rows and the query
surface the future Evidence Panel walks (``belief -> evidence -> source``);
M2 exercises it with hand-built fixtures rather than a real producer
(``mindtrace.domain.evidence`` module docstring).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from mindtrace.domain.enums import BeliefType, EvidenceSourceKind
from mindtrace.domain.evidence import Evidence


class EvidenceStore(Protocol):
    """An append-only collection of :class:`~mindtrace.domain.evidence.Evidence` edges."""

    def record(self, evidence: Evidence) -> Evidence:
        """Append ``evidence`` and return it. Never overwrites an existing id."""
        ...

    def for_belief(self, belief_type: BeliefType, belief_id: UUID) -> tuple[Evidence, ...]:
        """Every edge for ``(belief_type, belief_id)`` - the "why do you believe this?" query."""
        ...

    def for_source(self, source_kind: EvidenceSourceKind, source_id: UUID) -> tuple[Evidence, ...]:
        """Every edge citing ``(source_kind, source_id)`` - the reverse lookup deletion needs."""
        ...


class InMemoryEvidenceStore:
    """Process-local :class:`EvidenceStore`. Not thread-safe."""

    def __init__(self) -> None:
        """Start with an empty, append-only row list."""
        self._rows: list[Evidence] = []

    def record(self, evidence: Evidence) -> Evidence:
        """See :meth:`EvidenceStore.record`."""
        if any(row.id == evidence.id for row in self._rows):
            msg = f"evidence {evidence.id} already recorded (evidence is append-only)"
            raise ValueError(msg)
        self._rows.append(evidence)
        return evidence

    def for_belief(self, belief_type: BeliefType, belief_id: UUID) -> tuple[Evidence, ...]:
        """See :meth:`EvidenceStore.for_belief`."""
        return tuple(
            row
            for row in self._rows
            if row.belief_type == belief_type and row.belief_id == belief_id
        )

    def for_source(self, source_kind: EvidenceSourceKind, source_id: UUID) -> tuple[Evidence, ...]:
        """See :meth:`EvidenceStore.for_source`."""
        return tuple(
            row
            for row in self._rows
            if row.source_kind == source_kind and row.source_id == source_id
        )
