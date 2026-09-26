"""Persistence for refresh-token rotation state (M6-API).

:func:`find_by_token_hash` is a pre-authentication lookup - the caller does
not know ``user_id`` yet (that is exactly what presenting the token
establishes) - so a normal :func:`~mindtrace.db.session.user_scoped_session`
cannot be used, and a bare :func:`~mindtrace.db.session.get_session` would
see zero rows under RLS regardless of the ``WHERE`` clause. It calls the
narrow ``auth_lookup_refresh_token`` SECURITY DEFINER function
(``migrations/versions/0002_auth_and_idempotency.py``) instead - the same
pattern ``user_repository.find_user_by_email`` uses. Every other function
here already knows ``user_id`` (from that lookup, or from the caller's own
authenticated session) and goes through the normal RLS-enforced path.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text

from mindtrace.db.models.refresh_token import RefreshTokenModel
from mindtrace.db.session import get_session, user_scoped_session
from mindtrace.domain.ids import UserId
from mindtrace.domain.refresh_token import RefreshToken


def create(token: RefreshToken) -> None:
    """Insert one newly-issued refresh token."""
    with user_scoped_session(token.user_id) as session:
        session.add(_to_model(token))


def find_by_token_hash(token_hash: str) -> RefreshToken | None:
    """Find the row for a presented refresh token, by its hash. See module docstring."""
    with get_session() as session:
        row = (
            session.execute(
                text("SELECT * FROM auth_lookup_refresh_token(:token_hash)"),
                {"token_hash": token_hash},
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return RefreshToken(
            id=row["id"],
            user_id=UserId(row["user_id"]),
            family_id=row["family_id"],
            token_hash=token_hash,
            issued_at=row["issued_at"],
            expires_at=row["expires_at"],
            consumed_at=row["consumed_at"],
            revoked_at=row["revoked_at"],
            replaced_by=row["replaced_by"],
        )


def mark_consumed(*, user_id: UserId, token_id: UUID, replaced_by: UUID, now: datetime) -> None:
    """Mark one token consumed (rotated away) in favour of ``replaced_by``."""
    with user_scoped_session(user_id) as session:
        row = session.get(RefreshTokenModel, token_id)
        if row is not None:
            row.consumed_at = now
            row.replaced_by = replaced_by


def revoke_family(*, user_id: UserId, family_id: UUID, now: datetime) -> None:
    """Revoke every currently-active token in ``family_id`` (reuse detection)."""
    with user_scoped_session(user_id) as session:
        rows = session.execute(
            select(RefreshTokenModel).where(
                RefreshTokenModel.family_id == family_id,
                RefreshTokenModel.user_id == user_id,
                RefreshTokenModel.consumed_at.is_(None),
                RefreshTokenModel.revoked_at.is_(None),
            )
        ).scalars()
        for row in rows:
            row.revoked_at = now


def revoke_all_for_user(*, user_id: UserId, now: datetime) -> None:
    """Revoke every currently-active token for ``user_id``.

    Logout (M6-API planning s5): the documented ``POST /v1/auth/logout``
    takes no body, so there is no way to name a single session/family -
    this revokes every active family the user has.
    """
    with user_scoped_session(user_id) as session:
        rows = session.execute(
            select(RefreshTokenModel).where(
                RefreshTokenModel.user_id == user_id,
                RefreshTokenModel.consumed_at.is_(None),
                RefreshTokenModel.revoked_at.is_(None),
            )
        ).scalars()
        for row in rows:
            row.revoked_at = now


def _to_model(token: RefreshToken) -> RefreshTokenModel:
    return RefreshTokenModel(
        id=token.id,
        user_id=token.user_id,
        family_id=token.family_id,
        token_hash=token.token_hash,
        issued_at=token.issued_at,
        expires_at=token.expires_at,
        consumed_at=token.consumed_at,
        revoked_at=token.revoked_at,
        replaced_by=token.replaced_by,
    )
