"""Tests for ``mindtrace.config`` (environment-driven settings)."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from mindtrace.config import MASTER_KEY_LENGTH, MasterKeyConfigError, Settings, get_settings
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
    assert settings.database_url is None
    assert settings.master_key is None


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


def test_constructing_settings_never_requires_database_or_master_key() -> None:
    """Unrelated callers (schema_dir, app_name) must never be forced to configure
    persistence/crypto just to construct ``Settings`` (M6-Persistence/Foundation
    planning s4)."""
    Settings()  # must not raise


class TestMasterKeyBytes:
    def test_unset_master_key_fails_closed(self) -> None:
        with pytest.raises(MasterKeyConfigError, match="not set"):
            Settings().master_key_bytes()

    def test_valid_base64_32_bytes_decodes_correctly(self, monkeypatch: Any) -> None:
        raw = b"\x2a" * MASTER_KEY_LENGTH
        monkeypatch.setenv("MINDTRACE_MASTER_KEY", base64.b64encode(raw).decode("ascii"))
        assert Settings().master_key_bytes() == raw

    def test_invalid_base64_fails_closed(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("MINDTRACE_MASTER_KEY", "not-valid-base64!!!")
        with pytest.raises(MasterKeyConfigError, match="base64"):
            Settings().master_key_bytes()

    def test_wrong_decoded_length_fails_closed(self, monkeypatch: Any) -> None:
        too_short = base64.b64encode(b"\x00" * 16).decode("ascii")
        monkeypatch.setenv("MINDTRACE_MASTER_KEY", too_short)
        with pytest.raises(MasterKeyConfigError, match="32 bytes"):
            Settings().master_key_bytes()

    def test_never_returns_a_placeholder_key_on_failure(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("MINDTRACE_MASTER_KEY", "!!!")
        with pytest.raises(MasterKeyConfigError):
            Settings().master_key_bytes()
