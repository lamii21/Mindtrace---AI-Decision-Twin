"""Runtime settings.

The only place that reads process environment. Values are resolved once and
cached. The domain layer never imports this module -- engines and parsers take
their inputs explicitly (Invariant A).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from mindtrace.domain.paths import default_schema_dir


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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings`, constructed once."""
    return Settings()
