"""The provenance edge: what supports a belief, and where that support points.

``Evidence`` is a tier-B materialised snapshot (``docs/architecture/02-domain-model.md``
AG-9) - immutable once written, distinct from both the belief it supports and
the source it cites. It is the type the future Evidence Panel walks:
``belief -> evidence -> source -> (memory | decision | ...)``.

M2 has no belief-producing engine (no Preference/Trait/decision_factor exists
yet), so nothing in this milestone *writes* real evidence for a real belief.
What M2 provides is the type itself, an append-only store for it
(``mindtrace.events.evidence_store``), and the query surface a future engine
will use - proven with hand-built fixtures, never a placeholder engine
pretending to have derived something (M2 s18).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from mindtrace.domain.enums import BeliefType, EvidenceSourceKind, Polarity
from mindtrace.domain.ids import EvidenceId, UserId

_FrozenModel = ConfigDict(frozen=True, extra="forbid")


class Evidence(BaseModel):
    """One provenance edge: a belief, the source that justifies it, and how.

    ``belief_id`` and ``source_id`` are bare ``UUID`` rather than a typed alias
    on either side: ``belief_id`` names an entity from a belief-producing
    engine that doesn't exist in M2 (see module docstring); ``source_id``'s
    concrete type depends on ``source_kind`` (a ``MemoryId`` when
    ``source_kind == MEMORY``, otherwise an id this milestone never mints).
    """

    model_config = _FrozenModel

    id: EvidenceId
    user_id: UserId
    belief_type: BeliefType
    belief_id: UUID
    source_kind: EvidenceSourceKind
    source_id: UUID
    weight: float
    polarity: Polarity
    engine_version: str
    created_at: datetime
