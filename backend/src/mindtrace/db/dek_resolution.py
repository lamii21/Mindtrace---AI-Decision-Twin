"""The one place ``db/`` resolves a raw DEK from a session + a ``KeyProvider``.

Shared by :mod:`mindtrace.db.event_store` and every ``db/repositories/*.py``
that encrypts/decrypts a field, so "how do I get a DEK" has exactly one
implementation.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mindtrace.db.crypto import KeyProvider
from mindtrace.db.errors import KeyDestroyedError, KeyUnavailableError, UnknownUserError
from mindtrace.db.models.user import UserModel
from mindtrace.db.models.user_data_key import UserDataKeyModel
from mindtrace.domain.ids import UserId


def current_key_version(session: Session, *, user_id: UserId) -> int:
    """The ``key_version`` new writes for ``user_id`` should use.

    Raises:
        UnknownUserError: no ``users`` row for ``user_id``.
    """
    user_row = session.get(UserModel, user_id)
    if user_row is None:
        msg = f"no user {user_id}"
        raise UnknownUserError(msg)
    return user_row.data_key_ref


def resolve_dek(
    session: Session, *, user_id: UserId, key_version: int, key_provider: KeyProvider
) -> bytes:
    """Fetch the wrapped DEK for ``(user_id, key_version)`` and unwrap it.

    Raises:
        KeyUnavailableError: no ``user_data_key`` row exists for that
            ``(user_id, key_version)`` pair.
        KeyDestroyedError: the row exists but was crypto-shredded.
        db.crypto.CryptoError: the master key could not authenticate the
            wrapped bytes.
    """
    dek_row = session.execute(
        select(UserDataKeyModel).where(
            UserDataKeyModel.user_id == user_id, UserDataKeyModel.key_version == key_version
        )
    ).scalar_one_or_none()
    if dek_row is None:
        msg = f"no user_data_key for user {user_id} key_version={key_version}"
        raise KeyUnavailableError(msg)
    if dek_row.destroyed_at is not None:
        msg = f"user_data_key for user {user_id} key_version={key_version} was crypto-shredded"
        raise KeyDestroyedError(msg)
    return key_provider.unwrap_dek(
        dek_row.wrapped_dek, dek_row.nonce, user_id=user_id, key_version=key_version
    )
