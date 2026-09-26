"""``/v1/auth/*`` (``docs/api/08`` s2)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Response, status

from mindtrace.api.deps import get_auth_config, get_current_user_id, get_key_provider, now
from mindtrace.api.schemas.auth import (
    AuthUser,
    ConsentStateResponse,
    ConsentUpdate,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    TokenPairResponse,
)
from mindtrace.db.crypto import KeyProvider
from mindtrace.domain.ids import UserId
from mindtrace.services import auth_service
from mindtrace.services.auth_service import AuthConfig

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/register", response_model=AuthUser, status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterRequest,
    key_provider: KeyProvider = Depends(get_key_provider),
    request_time: datetime = Depends(now),
) -> AuthUser:
    """Create a new account."""
    user = auth_service.register(
        email=body.email,
        password=body.password.get_secret_value(),
        key_provider=key_provider,
        now=request_time,
    )
    return AuthUser(user_id=user.id, email=user.email, created_at=user.created_at)


@router.post("/login", response_model=TokenPairResponse)
def login(
    body: LoginRequest,
    config: AuthConfig = Depends(get_auth_config),
    request_time: datetime = Depends(now),
) -> TokenPairResponse:
    """Authenticate and issue a fresh access/refresh token pair."""
    pair = auth_service.login(
        email=body.email,
        password=body.password.get_secret_value(),
        config=config,
        now=request_time,
    )
    return TokenPairResponse(**pair.__dict__)


@router.post("/refresh", response_model=TokenPairResponse)
def refresh(
    body: RefreshRequest,
    config: AuthConfig = Depends(get_auth_config),
    request_time: datetime = Depends(now),
) -> TokenPairResponse:
    """Rotate a refresh token for a fresh access/refresh token pair."""
    pair = auth_service.refresh(refresh_token=body.refresh_token, config=config, now=request_time)
    return TokenPairResponse(**pair.__dict__)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    user_id: UserId = Depends(get_current_user_id),
    request_time: datetime = Depends(now),
) -> Response:
    """Revoke every active refresh-token family for the caller."""
    auth_service.logout(user_id=user_id, now=request_time)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=MeResponse)
def me(user_id: UserId = Depends(get_current_user_id)) -> MeResponse:
    """Return the caller's own account and current consent state."""
    user = auth_service.get_me(user_id)
    consents = auth_service.current_consent_state(user_id)
    return MeResponse(
        user_id=user.id,
        email=user.email,
        created_at=user.created_at,
        consents=[_to_consent_state(c) for c in consents],
    )


@router.put("/consent", response_model=ConsentStateResponse)
def set_consent(
    body: ConsentUpdate,
    user_id: UserId = Depends(get_current_user_id),
    request_time: datetime = Depends(now),
) -> ConsentStateResponse:
    """Append a new (immutable) consent record for one scope."""
    state = auth_service.set_consent(
        user_id=user_id,
        scope=body.scope,
        granted=body.granted,
        policy_version=auth_service.CONSENT_POLICY_VERSION,
        now=request_time,
    )
    return _to_consent_state(state)


def _to_consent_state(state: auth_service.ConsentState) -> ConsentStateResponse:
    return ConsentStateResponse(
        scope=state.scope,
        granted=state.granted,
        policy_version=state.policy_version,
        updated_at=state.updated_at,
    )
