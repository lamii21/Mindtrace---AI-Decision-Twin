"""M10 parallel-twin synthesis: one new nullable column on ``simulation``.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-13

Adds ``simulation.synthesis`` (JSONB, nullable) - the deterministic
weight-of-evidence vote across the parallel twins (ADR-007). Nullable so
every pre-M10 ``simulation`` row (persisted before this milestone, with only
one ``"base"`` entry in ``twin_configs`` and no vote to report) continues to
load as ``Simulation.synthesis = None`` exactly as it already does today -
no backfill, no re-derivation of history. Nothing else about ``simulation``
changes: ``twin_configs`` already stores a JSON *array* (0003) and needs no
schema change to hold 5 entries instead of 1. No RLS/grant change either -
``simulation`` keeps its existing append-only ``SELECT, INSERT`` grant; this
is a column addition, not a new write path.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable ``synthesis`` column."""
    op.add_column("simulation", sa.Column("synthesis", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    """Drop the ``synthesis`` column."""
    op.drop_column("simulation", "synthesis")
