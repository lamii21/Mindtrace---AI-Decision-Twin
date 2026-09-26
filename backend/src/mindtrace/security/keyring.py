"""Master-key wrap/unwrap for per-user DEKs (ADR-009).

Purely cryptographic: every function here takes already-fetched bytes and
returns bytes. Fetching/persisting the wrapped DEK is ``db/``'s job (a plain
SQL query); this module never touches a database, a session, or a
``user_id``'s row - only the master key and the bytes handed to it. That is
what lets ``db`` and ``security`` stay mutually import-free: ``db/crypto.py``
declares the ``KeyProvider`` Protocol it needs, and the two classes here
(``EnvironmentKeyProvider``, ``FakeKeyProvider``) satisfy it structurally,
with no import of ``mindtrace.db`` in either direction.
"""

from __future__ import annotations

import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from mindtrace.domain.errors import DomainError
from mindtrace.domain.ids import UserId

MASTER_KEY_LENGTH = 32  # AES-256
DEK_LENGTH = 32
_WRAP_NONCE_LENGTH = 12


class KeyringError(DomainError):
    """Base class for every keyring failure. Always fail closed."""


class MasterKeyMalformedError(KeyringError):
    """The configured master key is not exactly :data:`MASTER_KEY_LENGTH` bytes."""


class DekUnwrapError(KeyringError):
    """A wrapped DEK could not be authenticated under the configured master key.

    Covers a tampered ``wrapped_dek``/``nonce`` and a DEK wrapped under a
    different master key (e.g. after a lost/rotated key with no re-wrap).
    """


def generate_dek() -> bytes:
    """A fresh, random 256-bit DEK for a newly-created user."""
    return os.urandom(DEK_LENGTH)


def _aad(*, user_id: UserId, key_version: int) -> bytes:
    return f"user_dek:{user_id}:{key_version}".encode()


class EnvironmentKeyProvider:
    """Wraps/unwraps per-user DEKs under a master key held in process memory.

    The dev/CI default (ADR-009): the master key comes from
    ``Settings.master_key`` (itself sourced from ``MINDTRACE_MASTER_KEY``),
    never from the database or the repo. A future ``KMSKeyProvider`` would
    satisfy the same ``db.crypto.KeyProvider`` Protocol by fetching the
    master key from a real KMS instead - not implemented in this milestone.
    """

    def __init__(self, master_key: bytes) -> None:
        """Validate ``master_key``'s length up front - fail closed, not on first use.

        Raises:
            MasterKeyMalformedError: ``master_key`` is not exactly
                :data:`MASTER_KEY_LENGTH` bytes.
        """
        if len(master_key) != MASTER_KEY_LENGTH:
            msg = f"master key must be exactly {MASTER_KEY_LENGTH} bytes, got {len(master_key)}"
            raise MasterKeyMalformedError(msg)
        self._master_key = master_key

    def wrap_dek(self, dek: bytes, *, user_id: UserId, key_version: int) -> tuple[bytes, bytes]:
        """See ``db.crypto.KeyProvider.wrap_dek``."""
        nonce = os.urandom(_WRAP_NONCE_LENGTH)
        aad = _aad(user_id=user_id, key_version=key_version)
        wrapped = AESGCM(self._master_key).encrypt(nonce, dek, aad)
        return wrapped, nonce

    def unwrap_dek(
        self, wrapped_dek: bytes, nonce: bytes, *, user_id: UserId, key_version: int
    ) -> bytes:
        """See ``db.crypto.KeyProvider.unwrap_dek``.

        Raises:
            DekUnwrapError: authentication failed.
        """
        aad = _aad(user_id=user_id, key_version=key_version)
        try:
            return AESGCM(self._master_key).decrypt(nonce, wrapped_dek, aad)
        except InvalidTag as exc:
            msg = f"failed to unwrap DEK for user {user_id} key_version={key_version}"
            raise DekUnwrapError(msg) from exc


class FakeKeyProvider(EnvironmentKeyProvider):
    """A deterministic, network-free provider for tests (ADR-009 s6).

    Fixed, in-process master key material - never reads ``MINDTRACE_MASTER_KEY``
    or any environment variable, so tests never depend on host configuration.
    """

    def __init__(self, *, seed: bytes = b"\x42" * MASTER_KEY_LENGTH) -> None:
        """Build a provider fixed on ``seed``.

        ``seed`` must already be :data:`MASTER_KEY_LENGTH` bytes - no
        hashing/stretching, so two ``FakeKeyProvider()`` instances always
        agree byte-for-byte.
        """
        super().__init__(seed)


__all__ = [
    "DEK_LENGTH",
    "MASTER_KEY_LENGTH",
    "DekUnwrapError",
    "EnvironmentKeyProvider",
    "FakeKeyProvider",
    "KeyringError",
    "MasterKeyMalformedError",
    "generate_dek",
]
