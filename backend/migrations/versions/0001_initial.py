"""M6-Persistence/Foundation initial schema.

Creates users, user_data_key, consent_record, memory_event, memory,
decision - RLS, append-only enforcement.

Revision ID: 0001
Revises:
Create Date: 2026-09-26

Role bootstrap (``CREATE ROLE mindtrace_app``) lives in
``infra/postgres/init.sql``, not here - cluster-level role creation and
schema migration are deliberately kept separate (M6-Persistence/Foundation
planning s22). This migration only grants/revokes table-level privileges to
a role it assumes already exists; if it does not, the GRANT statements below
fail loudly rather than silently succeeding with no effect.

Every RLS policy reads ``NULLIF(current_setting('app.user_id', true), '')``
- two guards, not one. ``missing_ok=true`` covers a GUC that was truly never
touched this session (returns SQL ``NULL``). ``NULLIF(..., '')`` covers the
case that actually occurs on a *pooled, reused* connection: once
``app.user_id`` has been ``SET LOCAL``-scoped once, PostgreSQL resets a
custom (placeholder) GUC to the empty string ``''`` - not ``NULL`` - at the
end of that transaction, not to "never set". Casting ``''::uuid`` directly
raises ``invalid input syntax for type uuid``, which would turn "forgot to
scope the session" into a hard error instead of ADR-008's intended zero-rows
fail-closed behaviour; ``NULLIF`` converts that empty string to ``NULL``
first so the same ``column = NULL`` -> zero-rows path handles both cases
uniformly.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_APP_ROLE = "mindtrace_app"

# (table, tenant_column) - tenant_column is what each policy compares
# against NULLIF(current_setting('app.user_id', true), '')::uuid.
_RLS_TABLES: tuple[tuple[str, str], ...] = (
    ("users", "id"),
    ("user_data_key", "user_id"),
    ("consent_record", "user_id"),
    ("memory_event", "user_id"),
    ("memory", "user_id"),
    ("decision", "user_id"),
)


def upgrade() -> None:
    """Create this milestone's schema, RLS policies, and application-role grants."""
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("data_key_ref", sa.Integer(), nullable=False),
        sa.Column("next_event_seq", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "user_data_key",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("wrapped_dek", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("destroyed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "key_version", name="uq_user_data_key_version"),
    )

    op.create_table(
        "consent_record",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_consent_record_user_id", "consent_record", ["user_id"])

    op.create_table(
        "memory_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("causation_id", sa.Uuid(), nullable=True),
        sa.Column("correlation_id", sa.Uuid(), nullable=True),
        sa.UniqueConstraint("user_id", "seq", name="uq_memory_event_user_seq"),
    )

    op.create_table(
        "memory",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.Date(), nullable=True),
        sa.Column("origin_event_seq", sa.Integer(), nullable=False),
        sa.Column("superseded_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_event_seq", sa.Integer(), nullable=True),
        sa.Column("projector_version", sa.Text(), nullable=False),
    )
    op.create_index("ix_memory_user_id", "memory", ["user_id"])
    op.create_index("ix_memory_user_id_type", "memory", ["user_id", "type"])
    op.create_index("ix_memory_user_id_source", "memory", ["user_id", "source"])

    op.create_table(
        "decision",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.LargeBinary(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("context", sa.LargeBinary(), nullable=False),
        sa.Column("options", sa.LargeBinary(), nullable=False),
        sa.Column("chosen_option", sa.Text(), nullable=True),
        sa.Column("reasoning", sa.LargeBinary(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_decision_user_id", "decision", ["user_id"])
    op.create_index("ix_decision_user_id_category", "decision", ["user_id", "category"])
    op.create_index("ix_decision_user_id_status", "decision", ["user_id", "status"])

    _enable_rls()
    _grant_app_role_privileges()


def downgrade() -> None:
    """Reverse :func:`upgrade` exactly: grants, policies, then tables in dependency order."""
    _revoke_app_role_privileges()

    for table, _column in reversed(_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")

    op.drop_table("decision")
    op.drop_table("memory")
    op.drop_table("memory_event")
    op.drop_table("consent_record")
    op.drop_table("user_data_key")
    op.drop_table("users")


def _enable_rls() -> None:
    for table, column in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # FORCE, not just ENABLE: without it, RLS is skipped for the table's
        # *owner* (the role Alembic itself runs as) - FORCE makes the policy
        # apply to every role, so this migration's own author role cannot
        # accidentally count as "trusted" (M6-Persistence/Foundation
        # planning s20).
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
                USING ({column} = NULLIF(current_setting('app.user_id', true), '')::uuid)
                WITH CHECK ({column} = NULLIF(current_setting('app.user_id', true), '')::uuid)
            """
        )


def _grant_app_role_privileges() -> None:
    op.execute(f"GRANT USAGE ON SCHEMA public TO {_APP_ROLE}")
    # No DELETE anywhere - nothing in this milestone deletes a row, and
    # withholding the grant entirely is a stronger guarantee than relying on
    # application code never issuing one (M6-Persistence/Foundation planning
    # s21).
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON users TO {_APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON user_data_key TO {_APP_ROLE}")
    # Append-only: no UPDATE, no DELETE.
    op.execute(f"GRANT SELECT, INSERT ON consent_record TO {_APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON memory_event TO {_APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON memory TO {_APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON decision TO {_APP_ROLE}")


def _revoke_app_role_privileges() -> None:
    for table in ("decision", "memory", "memory_event", "consent_record", "user_data_key", "users"):
        op.execute(f"REVOKE ALL ON {table} FROM {_APP_ROLE}")
