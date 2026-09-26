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


class MasterKeyConfigError(DomainError):
    """``MINDTRACE_MASTER_KEY`` is set but is not valid base64-encoded 32 bytes."""


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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings`, constructed once."""
    return Settings()
