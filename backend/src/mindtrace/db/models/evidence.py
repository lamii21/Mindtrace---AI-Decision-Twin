"""The ``evidence`` table - the Postgres adapter behind ``events.evidence_store.EvidenceStore``.

M2 defined the ``Evidence`` domain type and the ``EvidenceStore`` Protocol
with only an in-memory implementation (no belief-producing engine existed to
write real rows yet). M7 is the first real producer: each simulation writes
one ``decision_factor`` edge citing the decision whose context the
extraction ran against (M7 planning s15 - no memory-to-preference pipeline
exists yet to cite instead). Field-for-field identical to
``domain.evidence.Evidence``; plaintext (categorical ids/floats only, ADR-009).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from mindtrace.db.base import Base


class EvidenceModel(Base):
    """One immutable provenance edge."""

    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    belief_type: Mapped[str] = mapped_column(Text, nullable=False)
    belief_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    polarity: Mapped[str] = mapped_column(Text, nullable=False)
    engine_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
