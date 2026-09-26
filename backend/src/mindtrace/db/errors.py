"""Typed persistence-layer failures.

Distinct from ``db.crypto``'s cryptographic errors: these name *why a key
could not even be looked up*, not why decryption under a resolved key
failed.
"""

from __future__ import annotations

from mindtrace.domain.errors import DomainError


class PersistenceError(DomainError):
    """Base class for every ``db/`` failure that is not a crypto failure."""


class UnknownUserError(PersistenceError):
    """The referenced ``user_id`` has no row in ``users``."""


class KeyUnavailableError(PersistenceError):
    """No ``user_data_key`` row exists for the requested ``(user_id, key_version)``."""


class KeyDestroyedError(PersistenceError):
    """The ``user_data_key`` row exists but was crypto-shredded (``destroyed_at`` set)."""
