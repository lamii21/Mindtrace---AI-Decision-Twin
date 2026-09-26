"""The ``decision`` table - AG-5, pre-``simulate`` shape only.

``extracted_factors``/``extraction_model_run_id``/prediction/outcome links
are M7+/M8+ columns and are deliberately absent (M6-Persistence planning
review): adding them now, unwritten, would be exactly the "looks computed
but isn't" placeholder principle 15 warns against. ``title``/``context``/
``options``/``reasoning`` are encrypted envelopes (ADR-009); ``category``/
``status``/``chosen_option`` stay plaintext because
``GET /v1/decisions?category=&status=`` filters on them and
``chosen_option`` is a short id token, not prose.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, LargeBinary, Text
from sqlalchemy.orm import Mapped, mapped_column

from mindtrace.db.base import Base


class DecisionModel(Base):
    """One situation a user is weighing."""

    __tablename__ = "decision"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    options: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    chosen_option: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
