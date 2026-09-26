"""Persistence for AG-1's ``User``/``user_data_key``.

``create_user`` is the one legitimate case where a session's ``app.user_id``
is set to an id that does not exist yet: the new user's own id, asserted by
the caller as part of creating that exact row. This is the app role
declaring "I am about to act as this brand-new user" for a self-insert -
never a superuser/bypass role (M6-Persistence/Foundation planning s5/s20).
Both the ``users`` row and its first ``user_data_key`` row are written in
one transaction, so a user is never observable without a working key.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select

from mindtrace.db.crypto import KeyProvider
from mindtrace.db.models.user import UserModel
from mindtrace.db.models.user_data_key import UserDataKeyModel
from mindtrace.db.session import user_scoped_session
from mindtrace.domain.enums import UserStatus
from mindtrace.domain.ids import UserId
from mindtrace.domain.user import User

_INITIAL_KEY_VERSION = 1


def create_user(*, user: User, dek: bytes, key_provider: KeyProvider) -> None:
    """Insert ``user`` and wrap+persist ``dek`` as its first (``key_version=1``) DEK.

    ``user.data_key_ref`` must equal :data:`_INITIAL_KEY_VERSION` - this
    function does not renumber it.
    """
    wrapped_dek, nonce = key_provider.wrap_dek(dek, user_id=user.id, key_version=user.data_key_ref)
    with user_scoped_session(user.id) as session:
        session.add(
            UserModel(
                id=user.id,
                email=user.email,
                password_hash=user.password_hash,
                status=user.status.value,
                data_key_ref=user.data_key_ref,
                next_event_seq=1,
                created_at=user.created_at,
                deleted_at=user.deleted_at,
            )
        )
        session.add(
            UserDataKeyModel(
                id=uuid4(),
                user_id=user.id,
                key_version=user.data_key_ref,
                wrapped_dek=wrapped_dek,
                nonce=nonce,
                created_at=user.created_at,
            )
        )


def get_user(user_id: UserId) -> User | None:
    """Return ``user_id``'s row, or ``None`` if it does not exist / is not visible (RLS)."""
    with user_scoped_session(user_id) as session:
        row = session.get(UserModel, user_id)
        if row is None:
            return None
        return _to_domain(row)


def destroy_user_data_key(*, user_id: UserId, key_version: int, destroyed_at: datetime) -> bool:
    """Crypto-shred: mark one wrapped DEK generation destroyed.

    Never touches ``memory_event``/``memory``/``decision`` rows - every row
    that DEK ever encrypted becomes permanently unreadable by this call
    alone (ADR-009). Returns ``True`` if a row was found and marked,
    ``False`` if no such ``(user_id, key_version)`` row exists.
    """
    with user_scoped_session(user_id) as session:
        row = session.execute(
            select(UserDataKeyModel).where(
                UserDataKeyModel.user_id == user_id, UserDataKeyModel.key_version == key_version
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        row.destroyed_at = destroyed_at
        return True


def _to_domain(row: UserModel) -> User:
    return User(
        id=UserId(row.id),
        email=row.email,
        password_hash=row.password_hash,
        status=UserStatus(row.status),
        data_key_ref=row.data_key_ref,
        created_at=row.created_at,
        deleted_at=row.deleted_at,
    )
