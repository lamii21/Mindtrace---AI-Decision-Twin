"""M6-API auth/idempotency schema.

Adds refresh-token rotation state, idempotency keys, and the one SECURITY
DEFINER lookup login needs.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-30

**Why a SECURITY DEFINER function (``auth_lookup_by_email``).** ``users`` RLS
(0001) requires ``app.user_id`` to already be set, but login is the one
operation where the caller does not yet know their own id - that is exactly
what they are trying to establish. This is not a general RLS bypass: the
function is narrow (SQL-only, one predicate, returns exactly the four
columns authentication needs), grants no broader table access to
``mindtrace_app``, and every other query against ``users`` (and every query
against every other table) still goes through the normal RLS-enforced path.
Registration does not need this function: a duplicate email is caught by
``users``'s own ``UNIQUE(email)`` constraint, which PostgreSQL enforces
against all physical rows regardless of RLS visibility.

``refresh_token``/``idempotency_key`` are both user-owned tables and get the
same ``tenant_isolation`` RLS policy as every 0001 table. Neither is
append-only in the ``memory_event`` sense (a refresh token is legitimately
mutated in place to record consumption/revocation), so ``mindtrace_app``
receives ``UPDATE`` on ``refresh_token`` but still no ``DELETE`` anywhere.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_APP_ROLE = "mindtrace_app"


def upgrade() -> None:
    """Create refresh_token/idempotency_key, their RLS, grants, and the login lookup function."""
    op.create_table(
        "refresh_token",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by", sa.Uuid(), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_refresh_token_token_hash"),
    )
    op.create_index("ix_refresh_token_user_id", "refresh_token", ["user_id"])
    op.create_index("ix_refresh_token_family_id", "refresh_token", ["family_id"])

    op.create_table(
        "idempotency_key",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("route", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_fingerprint", sa.Text(), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "route", "idempotency_key", name="uq_idempotency_key_scope"),
    )

    for table in ("refresh_token", "idempotency_key"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
                USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
                WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
            """
        )

    op.execute(f"GRANT SELECT, INSERT, UPDATE ON refresh_token TO {_APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON idempotency_key TO {_APP_ROLE}")

    op.execute(
        """
        CREATE FUNCTION auth_lookup_by_email(p_email text)
        RETURNS TABLE(id uuid, password_hash text, status text, data_key_ref integer)
        LANGUAGE sql SECURITY DEFINER SET search_path = public STABLE AS $$
            SELECT id, password_hash, status, data_key_ref FROM users WHERE email = p_email
        $$
        """
    )
    op.execute(f"GRANT EXECUTE ON FUNCTION auth_lookup_by_email(text) TO {_APP_ROLE}")

    # The same problem, one layer down: presenting a refresh token to
    # POST /v1/auth/refresh is *also* a pre-authentication lookup - the
    # caller does not know their own user_id until the token identifies them
    # (M6-API planning). A bare, unscoped session sees zero refresh_token
    # rows under RLS regardless of the WHERE clause, so this needs the same
    # narrow SECURITY DEFINER carve-out as auth_lookup_by_email, not a
    # session-level bypass.
    op.execute(
        """
        CREATE FUNCTION auth_lookup_refresh_token(p_token_hash text)
        RETURNS TABLE(
            id uuid, user_id uuid, family_id uuid, issued_at timestamptz,
            expires_at timestamptz, consumed_at timestamptz, revoked_at timestamptz,
            replaced_by uuid
        )
        LANGUAGE sql SECURITY DEFINER SET search_path = public STABLE AS $$
            SELECT id, user_id, family_id, issued_at, expires_at, consumed_at,
                   revoked_at, replaced_by
            FROM refresh_token WHERE token_hash = p_token_hash
        $$
        """
    )
    op.execute(f"GRANT EXECUTE ON FUNCTION auth_lookup_refresh_token(text) TO {_APP_ROLE}")


def downgrade() -> None:
    """Reverse :func:`upgrade` exactly."""
    op.execute(f"REVOKE EXECUTE ON FUNCTION auth_lookup_refresh_token(text) FROM {_APP_ROLE}")
    op.execute("DROP FUNCTION auth_lookup_refresh_token(text)")
    op.execute(f"REVOKE EXECUTE ON FUNCTION auth_lookup_by_email(text) FROM {_APP_ROLE}")
    op.execute("DROP FUNCTION auth_lookup_by_email(text)")

    op.execute(f"REVOKE ALL ON idempotency_key FROM {_APP_ROLE}")
    op.execute(f"REVOKE ALL ON refresh_token FROM {_APP_ROLE}")

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON idempotency_key")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON refresh_token")

    op.drop_table("idempotency_key")
    op.drop_table("refresh_token")
