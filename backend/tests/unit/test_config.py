"""Tests for ``mindtrace.config`` (environment-driven settings)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from mindtrace.config import Settings, get_settings
from tests.support.schema_factories import REAL_SCHEMA_DIR


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """``get_settings`` is process-cached; isolate each test's environment."""
    get_settings.cache_clear()


def test_defaults() -> None:
    settings = Settings()
    assert settings.app_name == "mindtrace"
    assert settings.environment == "dev"
    assert settings.schema_dir == REAL_SCHEMA_DIR


def test_env_prefix_overrides_defaults(monkeypatch: Any) -> None:
    monkeypatch.setenv("MINDTRACE_APP_NAME", "mindtrace-ci")
    monkeypatch.setenv("MINDTRACE_ENVIRONMENT", "ci")
    settings = Settings()
    assert settings.app_name == "mindtrace-ci"
    assert settings.environment == "ci"


def test_unprefixed_env_var_is_ignored(monkeypatch: Any) -> None:
    monkeypatch.setenv("APP_NAME", "should-not-apply")
    assert Settings().app_name == "mindtrace"


def test_invalid_environment_value_rejected(monkeypatch: Any) -> None:
    monkeypatch.setenv("MINDTRACE_ENVIRONMENT", "production")  # not one of dev|ci|prod
    with pytest.raises(ValidationError, match="environment"):
        Settings()


def test_schema_dir_env_override(tmp_path: Path, monkeypatch: Any) -> None:
    fake_dir = tmp_path / "schema"
    fake_dir.mkdir()
    monkeypatch.setenv("MINDTRACE_SCHEMA_DIR", str(fake_dir))
    assert Settings().schema_dir == fake_dir


def test_settings_are_frozen() -> None:
    settings = Settings()
    with pytest.raises(ValidationError):
        settings.app_name = "changed"  # type: ignore[misc]


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_get_settings_cache_clear_reflects_new_environment(monkeypatch: Any) -> None:
    first = get_settings()
    monkeypatch.setenv("MINDTRACE_APP_NAME", "changed-after-cache")
    assert get_settings() is first  # still cached

    get_settings.cache_clear()
    assert get_settings().app_name == "changed-after-cache"
