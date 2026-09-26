"""Authentication primitives (M6-API): password hashing and JWT access tokens.

Pure, DB-free functions - the same layer-1 purity ``keyring.py`` already
keeps: no repository call, no session, no ``user_id`` lookup by email. The
distinction from ``keyring.py`` is responsibility, not layering - this module
proves *who is asking*; ``keyring.py`` proves *which bytes may decrypt this
user's data*. Neither imports the other.

**Access vs. refresh, by construction, not by a claim comparison.** The
access token is a signed JWT (stateless, short-lived, ``docs/api/08`` s1:
"~30 min"). The refresh token is a random opaque string with no JWT
structure at all - server-side state (a hash, in ``db.repositories.
refresh_token_repository``) is what makes it revocable. Handing a refresh
token to :func:`decode_access_token` fails at the JWT-parsing step, not at a
claim check that a bug could get wrong - "wrong token type" cannot silently
succeed.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

from mindtrace.domain.errors import DomainError
from mindtrace.domain.ids import UserId

REFRESH_TOKEN_BYTES = 32
_ACCESS_TOKEN_TYPE = "access"

_password_hasher = PasswordHasher()


class AuthError(DomainError):
    """Base class for every authentication failure. Always fail closed."""


class InvalidCredentialsError(AuthError):
    """The email/password pair does not authenticate.

    Deliberately the *same* error for "no such email" and "wrong password" -
    distinguishing them would let a caller enumerate registered emails.
    """


class TokenError(AuthError):
    """Base class for access-token failures."""


class TokenMalformedError(TokenError):
    """The token is not a well-formed, correctly-signed JWT of this type."""


class TokenExpiredError(TokenError):
    """The token's ``exp`` claim is in the past."""


def hash_password(password: str) -> str:
    """Argon2id-hash ``password``. Never logs or returns the plaintext."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-effort verification via argon2-cffi. Never raises on mismatch."""
    try:
        return _password_hasher.verify(password_hash, password)
    except VerificationError:
        return False


def create_access_token(
    user_id: UserId, *, secret: bytes, algorithm: str, ttl_seconds: int, now: datetime
) -> str:
    """Sign a short-lived access token for ``user_id``.

    Claims: ``sub`` (the user id), ``type="access"`` (defence in depth - even
    though a refresh token can never reach :func:`decode_access_token` as a
    parseable JWT at all), ``iat``, ``exp``.
    """
    payload = {
        "sub": str(user_id),
        "type": _ACCESS_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(token: str, *, secret: bytes, algorithm: str, now: datetime) -> UserId:
    """Verify and decode an access token, returning its subject.

    Expiry is checked against the caller-supplied ``now``, not PyJWT's own
    internal wall-clock read (``options={"verify_exp": False}`` below,
    checked manually) - the one place this module would otherwise silently
    violate Invariant A (:func:`create_access_token` already takes ``now``
    explicitly; the decode side must too, for the same reason and for
    deterministic tests).

    Raises:
        TokenExpiredError: the token's ``exp`` has passed as of ``now``.
        TokenMalformedError: the token is not a validly-signed JWT of the
            expected type, or its subject is not a UUID.
    """
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm], options={"verify_exp": False})
    except jwt.InvalidTokenError as exc:
        msg = "access token is malformed or has an invalid signature"
        raise TokenMalformedError(msg) from exc

    try:
        expires_at = payload["exp"]
    except KeyError as exc:
        msg = "access token has no expiration claim"
        raise TokenMalformedError(msg) from exc
    if expires_at <= now.timestamp():
        msg = "access token has expired"
        raise TokenExpiredError(msg)

    if payload.get("type") != _ACCESS_TOKEN_TYPE:
        msg = "token is not an access token"
        raise TokenMalformedError(msg)
    try:
        return _parse_user_id(payload["sub"])
    except (KeyError, ValueError) as exc:
        msg = "access token subject is not a valid user id"
        raise TokenMalformedError(msg) from exc


def generate_refresh_token() -> str:
    """A fresh, high-entropy opaque refresh token. Never a JWT, never predictable."""
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    """The value actually persisted for a refresh token - never the raw token itself."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _parse_user_id(value: object) -> UserId:
    if not isinstance(value, str):
        raise ValueError(value)
    return UserId(UUID(value))


__all__ = [
    "REFRESH_TOKEN_BYTES",
    "AuthError",
    "InvalidCredentialsError",
    "TokenError",
    "TokenExpiredError",
    "TokenMalformedError",
    "create_access_token",
    "decode_access_token",
    "generate_refresh_token",
    "hash_password",
    "hash_refresh_token",
    "verify_password",
]
