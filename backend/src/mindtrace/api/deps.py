"""Dependency injection: settings-derived config and the current-user dependency.

``now()`` is the one wall-clock read this request boundary is allowed
(Invariant A) - read once per request and passed explicitly to every
service call from there on.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mindtrace.config import get_settings
from mindtrace.db.crypto import KeyProvider
from mindtrace.domain.ids import UserId
from mindtrace.llm.client import LLMClient
from mindtrace.llm.providers.unavailable import UnavailableLLMClient
from mindtrace.security.auth import decode_access_token
from mindtrace.security.keyring import EnvironmentKeyProvider
from mindtrace.services.auth_service import AuthConfig

_bearer_scheme = HTTPBearer(auto_error=True)


def now() -> datetime:
    """The request's ``now``, read once. Every service function takes it explicitly."""
    return datetime.now(UTC)


@lru_cache(maxsize=1)
def _cached_key_provider() -> EnvironmentKeyProvider:
    return EnvironmentKeyProvider(get_settings().master_key_bytes())


def get_key_provider() -> KeyProvider:
    """The process-wide :class:`~mindtrace.security.keyring.EnvironmentKeyProvider`."""
    return _cached_key_provider()


def reset_key_provider_cache_for_tests() -> None:
    """Clear the cached key provider.

    Test teardown only, so a later test's different ``MINDTRACE_MASTER_KEY``
    is actually picked up.
    """
    _cached_key_provider.cache_clear()


def get_llm_client() -> LLMClient:
    """The process-wide ``LLMClient`` (M7 planning s9).

    No real provider adapter exists in this build - see
    ``llm/providers/unavailable.py``'s module docstring for exactly what
    that means and how a real provider gets wired in later.
    """
    return UnavailableLLMClient()


def get_auth_config() -> AuthConfig:
    """Build :class:`~mindtrace.services.auth_service.AuthConfig` from ``Settings``."""
    settings = get_settings()
    return AuthConfig(
        jwt_secret=settings.jwt_secret_bytes(),
        jwt_algorithm=settings.jwt_algorithm,
        access_token_ttl_seconds=settings.access_token_ttl_seconds,
        refresh_token_ttl_seconds=settings.refresh_token_ttl_seconds,
    )


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    request_time: datetime = Depends(now),
) -> UserId:
    """Decode and verify the ``Authorization: Bearer`` access token.

    Raises (propagate to ``api/errors.py``'s handlers):
        security.auth.TokenExpiredError / TokenMalformedError -> 401.
    """
    settings = get_settings()
    return decode_access_token(
        credentials.credentials,
        secret=settings.jwt_secret_bytes(),
        algorithm=settings.jwt_algorithm,
        now=request_time,
    )
