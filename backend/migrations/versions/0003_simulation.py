"""M7 simulation persistence: simulation, prediction, evidence.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-29

Adds the three tables M7 needs to persist a real simulation run:
``simulation`` and ``prediction`` (AG-7/AG-8, tier B - immutable once
written), and ``evidence`` (AG-9, the Postgres adapter behind the
already-existing ``events.evidence_store.EvidenceStore`` Protocol - M2 built
only an in-memory implementation, this is its first real backing store).

None of the three carries an encrypted column (ADR-009): every field is
categorical/numeric provenance from M3/M4/M5/M6-A's own validated result
types - never the scenario text, never an LLM rationale-span excerpt (M7
planning s7). All three are strictly append-only, tighter than
``refresh_token`` (0002): ``mindtrace_app`` gets ``SELECT, INSERT`` only, no
``UPDATE``, no ``DELETE`` - matching ``memory_event``'s (0001) grant exactly,
since a simulation/prediction/evidence row is never revised in place, ever.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_APP_ROLE = "mindtrace_app"
_TABLES = ("simulation", "prediction", "evidence")


def upgrade() -> None:
    """Create simulation/prediction/evidence, their RLS, and their grants."""
    op.create_table(
        "simulation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision_id", sa.Uuid(), sa.ForeignKey("decision.id"), nullable=False),
        sa.Column("simulation_version", sa.Text(), nullable=False),
        sa.Column("scenario_content_hash", sa.Text(), nullable=False),
        sa.Column("extraction", postgresql.JSONB(), nullable=False),
        sa.Column("twin_configs", postgresql.JSONB(), nullable=False),
        sa.Column("model_confidence", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_simulation_user_id", "simulation", ["user_id"])
    op.create_index("ix_simulation_decision_id", "simulation", ["decision_id"])

    op.create_table(
        "prediction",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision_id", sa.Uuid(), sa.ForeignKey("decision.id"), nullable=False),
        sa.Column("simulation_id", sa.Uuid(), sa.ForeignKey("simulation.id"), nullable=False),
        sa.Column("twin_version_id", sa.Uuid(), nullable=True),
        sa.Column("predicted_decision", sa.Text(), nullable=False),
        sa.Column("uncertain_reason", sa.Text(), nullable=True),
        sa.Column("predicted_confidence", sa.Float(), nullable=False),
        sa.Column("credible_interval", postgresql.JSONB(), nullable=True),
        sa.Column("factor_contributions", postgresql.JSONB(), nullable=False),
        sa.Column("margin", sa.Float(), nullable=False),
        sa.Column("engine_version", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_prediction_user_id", "prediction", ["user_id"])
    op.create_index("ix_prediction_decision_id", "prediction", ["decision_id"])
    op.create_index("ix_prediction_simulation_id", "prediction", ["simulation_id"])

    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("belief_type", sa.Text(), nullable=False),
        sa.Column("belief_id", sa.Uuid(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("polarity", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evidence_user_id", "evidence", ["user_id"])
    op.create_index("ix_evidence_belief", "evidence", ["belief_type", "belief_id"])
    op.create_index("ix_evidence_source", "evidence", ["source_kind", "source_id"])

    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
                USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
                WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
            """
        )
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {_APP_ROLE}")


def downgrade() -> None:
    """Reverse :func:`upgrade` exactly."""
    for table in reversed(_TABLES):
        op.execute(f"REVOKE ALL ON {table} FROM {_APP_ROLE}")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")

    op.drop_table("evidence")
    op.drop_table("prediction")
    op.drop_table("simulation")
