"""Registration, login, refresh rotation, logout, consent (M6-API).

**Refresh-token model chosen (M6-API planning s5).** Access = a signed JWT
(stateless, ~30 min). Refresh = a random opaque string; only its SHA-256
hash is ever persisted (``db.repositories.refresh_token_repository``), in a
row that also carries a ``family_id`` shared by every token descended from
one login. On ``refresh``: if the presented token's row is not
``is_active`` (already consumed or revoked) or has expired, the entire
family is revoked and the caller gets :class:`~mindtrace.security.auth.
InvalidCredentialsError`-shaped denial - reuse of a stolen, already-rotated
token invalidates the whole chain, not just that one token. If active and
unexpired: mark it consumed, issue a new token in the *same* family, and
return a fresh access token alongside it. This satisfies the threat model's
"refresh-token reuse detection" requirement (``docs/10-security-threat-model``
T9) without needing a second datastore or a background job.

**Logout (M6-API planning s5).** ``POST /v1/auth/logout`` is documented with
no request body (``docs/api/08`` s2), so there is no way to name a single
session to revoke - this revokes every currently-active refresh-token family
the authenticated user has ("log out everywhere"), the only interpretation
the documented contract's shape actually supports.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from mindtrace.db.crypto import KeyProvider
from mindtrace.db.errors import DuplicateEmailError
from mindtrace.db.repositories import (
    consent_repository,
    refresh_token_repository,
    user_repository,
)
from mindtrace.domain.consent import ConsentRecord
from mindtrace.domain.enums import ConsentScope, UserStatus
from mindtrace.domain.ids import ConsentRecordId, UserId
from mindtrace.domain.refresh_token import RefreshToken
from mindtrace.domain.user import User
from mindtrace.security import auth as security_auth
from mindtrace.security.auth import InvalidCredentialsError
from mindtrace.security.keyring import generate_dek
from mindtrace.services.errors import EmailAlreadyRegisteredError, ResourceNotFoundError

CONSENT_POLICY_VERSION = "1"


@dataclass(frozen=True)
class AuthConfig:
    """The "how to sign/expire tokens" knobs.

    Read once from ``Settings`` at the API boundary and passed in explicitly
    - services stay config-agnostic (M6-API planning s3).
    """

    jwt_secret: bytes
    jwt_algorithm: str
    access_token_ttl_seconds: int
    refresh_token_ttl_seconds: int


@dataclass(frozen=True)
class TokenPair:
    """``docs/api/08`` s2 ``TokenPair``."""

    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


@dataclass(frozen=True)
class ConsentState:
    """``docs/api/08`` s2 ``ConsentState`` - the *latest* record for one scope."""

    scope: ConsentScope
    granted: bool
    policy_version: str
    updated_at: datetime


def register(*, email: str, password: str, key_provider: KeyProvider, now: datetime) -> User:
    """Create a new user with a fresh per-user DEK (ADR-009).

    Raises:
        EmailAlreadyRegisteredError: ``email`` already belongs to another user.
    """
    user = User(
        id=UserId(uuid4()),
        email=email,
        password_hash=security_auth.hash_password(password),
        status=UserStatus.ACTIVE,
        data_key_ref=1,
        created_at=now,
    )
    try:
        user_repository.create_user(user=user, dek=generate_dek(), key_provider=key_provider)
    except DuplicateEmailError as exc:
        msg = f"email {email!r} is already registered"
        raise EmailAlreadyRegisteredError(msg) from exc
    return user


def login(*, email: str, password: str, config: AuthConfig, now: datetime) -> TokenPair:
    """Verify credentials and issue a fresh access/refresh token pair.

    Raises:
        InvalidCredentialsError: the email/password pair does not
            authenticate - deliberately identical whether the email is
            unknown or the password is wrong.
    """
    credentials = user_repository.find_user_by_email(email)
    if credentials is None:
        msg = "invalid email or password"
        raise InvalidCredentialsError(msg)
    if not security_auth.verify_password(password, credentials.password_hash):
        msg = "invalid email or password"
        raise InvalidCredentialsError(msg)
    return _issue_new_family(user_id=credentials.id, config=config, now=now)


def refresh(*, refresh_token: str, config: AuthConfig, now: datetime) -> TokenPair:
    """Rotate a refresh token, detecting reuse of an already-consumed/revoked one.

    Raises:
        InvalidCredentialsError: the token is unknown, expired, or was
            already consumed/revoked (in the last case, its whole family is
            revoked as a side effect before raising).
    """
    token_hash = security_auth.hash_refresh_token(refresh_token)
    stored = refresh_token_repository.find_by_token_hash(token_hash)
    if stored is None:
        msg = "unknown refresh token"
        raise InvalidCredentialsError(msg)

    if not stored.is_active:
        # Reuse of an already-consumed/revoked token: the whole family is
        # compromised (or a client bug replayed a stale token) - revoke it
        # all rather than trusting any token from this chain again.
        refresh_token_repository.revoke_family(
            user_id=stored.user_id, family_id=stored.family_id, now=now
        )
        msg = "refresh token has already been used"
        raise InvalidCredentialsError(msg)
    if stored.expires_at <= now:
        msg = "refresh token has expired"
        raise InvalidCredentialsError(msg)

    new_id = uuid4()
    new_raw_token = security_auth.generate_refresh_token()
    new_token = RefreshToken(
        id=new_id,
        user_id=stored.user_id,
        family_id=stored.family_id,
        token_hash=security_auth.hash_refresh_token(new_raw_token),
        issued_at=now,
        expires_at=now + timedelta(seconds=config.refresh_token_ttl_seconds),
    )
    refresh_token_repository.create(new_token)
    refresh_token_repository.mark_consumed(
        user_id=stored.user_id, token_id=stored.id, replaced_by=new_id, now=now
    )
    access_token = security_auth.create_access_token(
        stored.user_id,
        secret=config.jwt_secret,
        algorithm=config.jwt_algorithm,
        ttl_seconds=config.access_token_ttl_seconds,
        now=now,
    )
    return TokenPair(
        access_token=access_token,
        refresh_token=new_raw_token,
        token_type="bearer",
        expires_in=config.access_token_ttl_seconds,
    )


def logout(*, user_id: UserId, now: datetime) -> None:
    """Revoke every active refresh-token family for ``user_id``. See module docstring."""
    refresh_token_repository.revoke_all_for_user(user_id=user_id, now=now)


def get_me(user_id: UserId) -> User:
    """Return the authenticated user's own row.

    Raises:
        ResourceNotFoundError: the user no longer exists (should not happen
            for a valid access token, but never trust a token over the
            database - M6-API planning).
    """
    user = user_repository.get_user(user_id)
    if user is None:
        msg = f"user {user_id} not found"
        raise ResourceNotFoundError(msg)
    return user


def set_consent(
    *, user_id: UserId, scope: ConsentScope, granted: bool, policy_version: str, now: datetime
) -> ConsentState:
    """Append one immutable consent record. Never updates a prior one (ADR-008 item 8)."""
    record = ConsentRecord(
        id=ConsentRecordId(uuid4()),
        user_id=user_id,
        scope=scope,
        granted=granted,
        policy_version=policy_version,
        at=now,
    )
    consent_repository.append_consent(record)
    return ConsentState(scope=scope, granted=granted, policy_version=policy_version, updated_at=now)


def current_consent_state(user_id: UserId) -> tuple[ConsentState, ...]:
    """The latest record per scope, derived from the full append-only history.

    Never mutates a historical row (M6-API planning s6) - this only reads
    ``consent_repository.list_consent`` (already returned oldest-first) and
    keeps the last one seen per scope.
    """
    latest: dict[ConsentScope, ConsentRecord] = {}
    for record in consent_repository.list_consent(user_id):
        latest[record.scope] = record
    return tuple(
        ConsentState(
            scope=record.scope,
            granted=record.granted,
            policy_version=record.policy_version,
            updated_at=record.at,
        )
        for record in latest.values()
    )


def _issue_new_family(*, user_id: UserId, config: AuthConfig, now: datetime) -> TokenPair:
    raw_token = security_auth.generate_refresh_token()
    token = RefreshToken(
        id=uuid4(),
        user_id=user_id,
        family_id=uuid4(),
        token_hash=security_auth.hash_refresh_token(raw_token),
        issued_at=now,
        expires_at=now + timedelta(seconds=config.refresh_token_ttl_seconds),
    )
    refresh_token_repository.create(token)
    access_token = security_auth.create_access_token(
        user_id,
        secret=config.jwt_secret,
        algorithm=config.jwt_algorithm,
        ttl_seconds=config.access_token_ttl_seconds,
        now=now,
    )
    return TokenPair(
        access_token=access_token,
        refresh_token=raw_token,
        token_type="bearer",
        expires_in=config.access_token_ttl_seconds,
    )


__all__ = [
    "AuthConfig",
    "ConsentState",
    "TokenPair",
    "current_consent_state",
    "get_me",
    "login",
    "logout",
    "refresh",
    "register",
    "set_consent",
]
