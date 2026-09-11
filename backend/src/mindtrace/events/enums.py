"""Event-sourcing vocabulary.

Kept separate from ``mindtrace.domain.enums`` on purpose
(``docs/architecture/01-repository-structure.md`` s3): this is vocabulary
*about the event log itself*, not general domain vocabulary other layers
reason about directly.
"""

from __future__ import annotations

from enum import StrEnum


class MemoryEventType(StrEnum):
    """The five event kinds ``docs/architecture/02-domain-model.md`` AG-2 approves.

    M2 defines typed payloads and projector handling for ``INGESTED``,
    ``CORRECTED``, and ``DELETED`` only (``mindtrace.events.types``). The other
    two are declared now - so the vocabulary is complete and switches over it
    can be exhaustive - but are otherwise untouched: nothing in M2 produces or
    projects them.
    """

    INGESTED = "ingested"
    CORRECTED = "corrected"
    DELETED = "deleted"
    ELICITATION_ANSWERED = "elicitation_answered"
    OUTCOME_RECORDED = "outcome_recorded"
