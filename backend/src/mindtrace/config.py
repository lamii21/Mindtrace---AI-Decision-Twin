"""Runtime settings.

The only place that reads process environment. Values are resolved once and
cached. The domain layer never imports this module -- engines and parsers take
their inputs explicitly (Invariant A).

``database_url``/``master_key`` are both optional at the ``Settings`` level
and validated only where they are actually used (``db.session.configure_engine``,
:meth:`Settings.master_key_bytes`) - constructing ``Settings()`` must never
fail, or require a database, just because an unrelated caller only wanted
``schema_dir`` (M6-Persistence/Foundation planning s4).
"""

from __future__ import annotations

import base64
import binascii
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from mindtrace.domain.errors import DomainError
from mindtrace.domain.paths import default_schema_dir

MASTER_KEY_LENGTH = 32  # AES-256, ADR-009
MIN_JWT_SECRET_LENGTH = 32  # 256 bits - enough entropy for HS256


class MasterKeyConfigError(DomainError):
    """``MINDTRACE_MASTER_KEY`` is set but is not valid base64-encoded 32 bytes."""


class JwtSecretConfigError(DomainError):
    """``MINDTRACE_JWT_SECRET`` is unset or shorter than :data:`MIN_JWT_SECRET_LENGTH`."""


class Settings(BaseSettings):
    """Environment-driven configuration (prefix ``MINDTRACE_``)."""

    model_config = SettingsConfigDict(
        env_prefix="MINDTRACE_",
        env_file=".env",
        extra="ignore",
        frozen=True,
    )

    app_name: str = "mindtrace"
    environment: Literal["dev", "ci", "prod"] = "dev"
    schema_dir: Path = Field(default_factory=default_schema_dir)
    database_url: str | None = None
    master_key: SecretStr | None = None
    jwt_secret: SecretStr | None = None
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 1800  # ~30 min, docs/api/08 s1
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 30  # 30 days - not specified by docs; a
    # reasonable, documented default for a rotating, revocable refresh token (M6-API planning)

    def master_key_bytes(self) -> bytes:
        """Decode ``master_key`` into exactly :data:`MASTER_KEY_LENGTH` raw bytes.

        Raises:
            MasterKeyConfigError: ``master_key`` is unset, not valid base64,
                or does not decode to exactly :data:`MASTER_KEY_LENGTH` bytes.
                Fails closed - never returns a placeholder key.
        """
        if self.master_key is None:
            msg = "MINDTRACE_MASTER_KEY is not set"
            raise MasterKeyConfigError(msg)
        try:
            decoded = base64.b64decode(self.master_key.get_secret_value(), validate=True)
        except binascii.Error as exc:
            msg = "MINDTRACE_MASTER_KEY is not valid base64"
            raise MasterKeyConfigError(msg) from exc
        if len(decoded) != MASTER_KEY_LENGTH:
            msg = (
                f"MINDTRACE_MASTER_KEY must decode to {MASTER_KEY_LENGTH} bytes, got {len(decoded)}"
            )
            raise MasterKeyConfigError(msg)
        return decoded

    def jwt_secret_bytes(self) -> bytes:
        """Return the raw JWT signing secret, encoded UTF-8.

        Raises:
            JwtSecretConfigError: ``jwt_secret`` is unset or shorter than
                :data:`MIN_JWT_SECRET_LENGTH` bytes. Fails closed - never
                signs a token with a placeholder secret.
        """
        if self.jwt_secret is None:
            msg = "MINDTRACE_JWT_SECRET is not set"
            raise JwtSecretConfigError(msg)
        secret = self.jwt_secret.get_secret_value().encode("utf-8")
        if len(secret) < MIN_JWT_SECRET_LENGTH:
            msg = f"MINDTRACE_JWT_SECRET must be at least {MIN_JWT_SECRET_LENGTH} bytes"
            raise JwtSecretConfigError(msg)
        return secret


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings`, constructed once."""
    return Settings()
