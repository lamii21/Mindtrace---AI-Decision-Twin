"""Field-level AEAD encryption at the repository boundary (ADR-009).

Explicit functions, not a SQLAlchemy ``TypeDecorator`` (ADR-004 correction):
``db/repositories/*.py`` and ``db/event_store.py`` call :func:`encrypt_field`/
:func:`decrypt_field` directly when translating between a domain object and
an ORM row - the encrypt/decrypt call is always visible at its call site,
and nothing here reaches into ORM session state to find a "current user".

:class:`KeyProvider` is the one thing this module needs from outside and
cannot import (``db`` and ``security`` are mutually isolated per ADR-009) -
a ``Protocol`` port, the same pattern ``mindtrace.events.store.EventStore``
already uses. ``mindtrace.security.keyring``'s ``EnvironmentKeyProvider``/
``FakeKeyProvider`` satisfy it structurally, without importing ``db``.
"""

from __future__ import annotations

import hashlib
import os
from typing import Protocol
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from mindtrace.db.types import (
    NONCE_LENGTH,
    EnvelopeFormatError,
    pack_envelope,
    unpack_envelope,
)
from mindtrace.domain.errors import DomainError
from mindtrace.domain.ids import UserId

DEK_LENGTH = 32  # AES-256


class CryptoError(DomainError):
    """Base class for every field-encryption failure. Always fail closed."""


class MalformedKeyError(CryptoError):
    """A DEK is not exactly :data:`DEK_LENGTH` bytes."""


class AuthenticationError(CryptoError):
    """Authenticated decryption failed.

    Covers every one of: wrong key (wrong user/DEK), wrong AAD (ciphertext
    moved to a different row/column/table/user), a tampered ciphertext, or a
    tampered nonce - AES-GCM does not distinguish these cases, and this
    module does not try to guess which one occurred.
    """


class KeyProvider(Protocol):
    """The one capability ``db/`` needs from a keyring it cannot import.

    Both directions of the master-key wrap operate on already-fetched bytes -
    neither method touches a database. The caller (a repository) is
    responsible for fetching/persisting ``wrapped_dek``/``nonce`` themselves;
    a :class:`KeyProvider` is purely cryptographic.
    """

    def wrap_dek(self, dek: bytes, *, user_id: UserId, key_version: int) -> tuple[bytes, bytes]:
        """Wrap a raw DEK under the master key. Returns ``(wrapped, nonce)``."""
        ...

    def unwrap_dek(
        self, wrapped_dek: bytes, nonce: bytes, *, user_id: UserId, key_version: int
    ) -> bytes:
        """Unwrap ``wrapped_dek`` back to the raw DEK.

        Raises:
            CryptoError: the master key cannot authenticate ``wrapped_dek``
                (tampered, or wrapped under a different master key/user).
        """
        ...


def _aad(*, table: str, column: str, user_id: UserId, row_id: UUID) -> bytes:
    """Bind ciphertext to exactly the cell it was encrypted for (ADR-009).

    A SHA-256 digest, not the raw concatenation: fixed length, and immune to
    ambiguity from a delimiter character appearing inside a component.
    """
    return hashlib.sha256(f"{table}.{column}:{user_id}:{row_id}".encode()).digest()


def encrypt_field(
    plaintext: str,
    *,
    dek: bytes,
    table: str,
    column: str,
    user_id: UserId,
    row_id: UUID,
    key_version: int,
) -> bytes:
    """Encrypt one sensitive field value for storage.

    A fresh random nonce is drawn on every call, so encrypting the same
    ``plaintext`` twice produces different stored bytes (ADR-009 s10).

    Raises:
        MalformedKeyError: ``dek`` is not exactly :data:`DEK_LENGTH` bytes.
    """
    if len(dek) != DEK_LENGTH:
        msg = f"DEK must be exactly {DEK_LENGTH} bytes, got {len(dek)}"
        raise MalformedKeyError(msg)
    nonce = os.urandom(NONCE_LENGTH)
    aad = _aad(table=table, column=column, user_id=user_id, row_id=row_id)
    ciphertext = AESGCM(dek).encrypt(nonce, plaintext.encode("utf-8"), aad)
    return pack_envelope(key_version=key_version, nonce=nonce, ciphertext=ciphertext)


def decrypt_field(
    envelope: bytes,
    *,
    dek: bytes,
    table: str,
    column: str,
    user_id: UserId,
    row_id: UUID,
) -> str:
    """Decrypt one stored envelope back to its plaintext.

    Raises:
        MalformedKeyError: ``dek`` is not exactly :data:`DEK_LENGTH` bytes.
        db.types.EnvelopeFormatError: ``envelope`` is not a well-formed
            envelope (too short, or a nonce of the wrong length).
        AuthenticationError: the wrong ``dek``, the wrong ``table``/
            ``column``/``user_id``/``row_id`` (AAD mismatch), or a tampered
            ciphertext/nonce. Never returns a placeholder - callers must
            treat this as fail-closed.
    """
    if len(dek) != DEK_LENGTH:
        msg = f"DEK must be exactly {DEK_LENGTH} bytes, got {len(dek)}"
        raise MalformedKeyError(msg)
    _format_version, _key_version, nonce, ciphertext = unpack_envelope(envelope)
    aad = _aad(table=table, column=column, user_id=user_id, row_id=row_id)
    try:
        plaintext = AESGCM(dek).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        msg = f"authenticated decryption failed for {table}.{column} row {row_id}"
        raise AuthenticationError(msg) from exc
    return plaintext.decode("utf-8")


__all__ = [
    "DEK_LENGTH",
    "AuthenticationError",
    "CryptoError",
    "EnvelopeFormatError",
    "KeyProvider",
    "MalformedKeyError",
    "decrypt_field",
    "encrypt_field",
]
