"""Auth request/response DTOs (``docs/api/08`` s2). Field names/shapes are exact."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

from mindtrace.domain.enums import ConsentScope

_FrozenExtraForbid = ConfigDict(extra="forbid")

_MIN_PASSWORD_LENGTH = 12


class RegisterRequest(BaseModel):
    """``POST /v1/auth/register`` request body."""

    model_config = _FrozenExtraForbid

    email: EmailStr
    password: SecretStr = Field(min_length=_MIN_PASSWORD_LENGTH)


class AuthUser(BaseModel):
    """``POST /v1/auth/register`` response body."""

    model_config = _FrozenExtraForbid

    user_id: UUID
    email: str
    created_at: datetime


class LoginRequest(BaseModel):
    """``POST /v1/auth/login`` request body."""

    model_config = _FrozenExtraForbid

    email: EmailStr
    password: SecretStr


class TokenPairResponse(BaseModel):
    """``POST /v1/auth/login`` and ``POST /v1/auth/refresh`` response body."""

    model_config = _FrozenExtraForbid

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    """``POST /v1/auth/refresh`` request body."""

    model_config = _FrozenExtraForbid

    refresh_token: str


class ConsentUpdate(BaseModel):
    """``PUT /v1/auth/consent`` request body."""

    model_config = _FrozenExtraForbid

    scope: ConsentScope
    granted: bool


class ConsentStateResponse(BaseModel):
    """One scope's latest consent state.

    ``PUT /v1/auth/consent`` response body, and one entry of
    ``MeResponse.consents``.
    """

    model_config = _FrozenExtraForbid

    scope: ConsentScope
    granted: bool
    policy_version: str
    updated_at: datetime


class MeResponse(BaseModel):
    """``GET /v1/auth/me`` response body."""

    model_config = _FrozenExtraForbid

    user_id: UUID
    email: str
    created_at: datetime
    consents: list[ConsentStateResponse]
