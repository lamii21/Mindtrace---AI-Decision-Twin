"""M8 persistent Twin/TwinVersion + interview session.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-01

Adds the three tables M8 needs: ``twin`` and ``twin_version`` (AG-6, tier
B - immutable once written), and ``interview_session`` (thin, mutable
operational state - the in-flight interview, not the answers themselves).

**No ``interview_answer`` table** (M8 planning s13/s17): interview answers
are ``elicitation_answered`` events in the *existing*, already-encrypted
``memory_event`` table (0001) - ``MemoryEventType.ELICITATION_ANSWERED``
was declared ahead of its producer back in M2, and ``PostgresEventStore.
append()`` is fully generic over ``EventPayload``, so no schema change was
needed there at all. This migration only adds what genuinely has no home
yet.

``twin_version`` is strictly append-only, matching ``simulation``/
``prediction``/``evidence`` (0003) exactly: ``mindtrace_app`` gets
``SELECT, INSERT`` only, no ``UPDATE``, no ``DELETE`` - a later interview
*appends* row N+1, it never revises row N. ``twin`` gets ``UPDATE`` too, but
only ever to advance ``next_twin_version`` (see below) - no repository code
updates ``name``/``user_id``. ``interview_session`` is mutable in place
(``UPDATE`` granted, no ``DELETE``), matching ``refresh_token`` (0002): it
is operational state about an in-flight interview, not a tier-A/B immutable
record.

**TwinVersion version-number concurrency** (M8 planning requirement s6):
``twin.next_twin_version`` is an atomic counter column, identical in spirit
to ``users.next_event_seq`` (0001) - allocated with one
``UPDATE twin SET next_twin_version = next_twin_version + 1 WHERE id = :id
RETURNING next_twin_version - 1``, which takes a row-level lock on that
twin's row for the transaction's duration. Two concurrent finalisations for
the *same* twin serialise on that lock and can never allocate the same
version number; finalisations for *different* twins (different users) lock
different rows and proceed fully in parallel. ``UNIQUE(twin_id, version)``
is kept as a second, belt-and-braces guarantee.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_APP_ROLE = "mindtrace_app"


def upgrade() -> None:
    """Create twin/twin_version/interview_session, their RLS, and their grants."""
    op.create_table(
        "twin",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("next_twin_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_twin_user_id"),
    )
    op.create_index("ix_twin_user_id", "twin", ["user_id"])

    op.create_table(
        "twin_version",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("twin_id", sa.Uuid(), sa.ForeignKey("twin.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("trait_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("weights", postgresql.JSONB(), nullable=False),
        sa.Column("dispositions", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.Text(), nullable=False),
        sa.Column("projection_version", sa.Text(), nullable=False),
        sa.Column("factor_schema_version", sa.Integer(), nullable=False),
        sa.Column("trait_schema_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("twin_id", "version", name="uq_twin_version_twin_id_version"),
    )
    op.create_index("ix_twin_version_user_id", "twin_version", ["user_id"])
    op.create_index("ix_twin_version_twin_id", "twin_version", ["twin_id"])

    op.create_table(
        "interview_session",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("twin_id", sa.Uuid(), sa.ForeignKey("twin.id"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resulting_twin_version_id", sa.Uuid(), nullable=True),
        sa.Column("interview_noise", sa.Float(), nullable=True),
    )
    op.create_index("ix_interview_session_user_id", "interview_session", ["user_id"])

    for table in ("twin", "twin_version", "interview_session"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
                USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
                WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
            """
        )

    # `twin` gets UPDATE *only* so `next_twin_version`'s atomic counter can
    # advance (the version-allocation lock, see module docstring) -
    # repository code never updates `name`/`user_id`. `twin_version` gets no
    # UPDATE at all: strictly append-only, matching `simulation`/
    # `prediction`/`evidence` (0003) exactly - there is no repository
    # function that could issue one.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON twin TO {_APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON twin_version TO {_APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON interview_session TO {_APP_ROLE}")


def downgrade() -> None:
    """Reverse :func:`upgrade` exactly."""
    for table in ("interview_session", "twin_version", "twin"):
        op.execute(f"REVOKE ALL ON {table} FROM {_APP_ROLE}")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")

    op.drop_table("interview_session")
    op.drop_table("twin_version")
    op.drop_table("twin")
