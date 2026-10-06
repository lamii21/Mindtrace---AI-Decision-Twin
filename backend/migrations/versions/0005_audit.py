"""M9 accountability ledger: ``audit_log``.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-06

Adds the one table M9 needs that has no existing home: ``audit_log``
(``docs/architecture/02-domain-model.md`` cross-cutting section) - tier A,
append-only, identical in enforcement shape to ``consent_record``/
``memory_event`` (0001): RLS + FORCE, ``mindtrace_app`` granted
``SELECT, INSERT`` only, no ``UPDATE``, no ``DELETE``. Written on every
M9 derivation (a memory deletion applied, a dispute resolved into a new
``TwinVersion``) - never the free text that drove it, only a
``payload_hash`` (see ``domain/audit.py``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_APP_ROLE = "mindtrace_app"


def upgrade() -> None:
    """Create ``audit_log``, its RLS policy, and its application-role grant."""
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("engine_version", sa.Text(), nullable=True),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_target", "audit_log", ["target_type", "target_id"])

    op.execute("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_log FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON audit_log
            USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
            WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
        """
    )

    # Append-only: no UPDATE, no DELETE - matching consent_record/memory_event.
    op.execute(f"GRANT SELECT, INSERT ON audit_log TO {_APP_ROLE}")


def downgrade() -> None:
    """Reverse :func:`upgrade` exactly."""
    op.execute(f"REVOKE ALL ON audit_log FROM {_APP_ROLE}")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON audit_log")
    op.drop_table("audit_log")
