"""Tests for the schema-directory resolution seam (``mindtrace.domain.paths``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mindtrace.domain.paths import default_schema_dir
from tests.support.schema_factories import REAL_SCHEMA_DIR


def test_finds_the_real_schema_dir_with_no_override(monkeypatch: Any) -> None:
    monkeypatch.delenv("MINDTRACE_SCHEMA_DIR", raising=False)
    assert default_schema_dir() == REAL_SCHEMA_DIR


def test_env_override_wins_over_the_walked_up_default(tmp_path: Path, monkeypatch: Any) -> None:
    fake_dir = tmp_path / "custom_schema"
    fake_dir.mkdir()
    monkeypatch.setenv("MINDTRACE_SCHEMA_DIR", str(fake_dir))
    assert default_schema_dir() == fake_dir.resolve()


def test_env_override_pointing_at_a_non_directory_raises(tmp_path: Path, monkeypatch: Any) -> None:
    not_a_dir = tmp_path / "not_a_directory.txt"
    not_a_dir.write_text("hello", encoding="utf-8")
    monkeypatch.setenv("MINDTRACE_SCHEMA_DIR", str(not_a_dir))
    with pytest.raises(FileNotFoundError, match="does not point to a directory"):
        default_schema_dir()


def test_env_override_pointing_at_a_missing_path_raises(tmp_path: Path, monkeypatch: Any) -> None:
    missing = tmp_path / "does_not_exist_at_all"
    monkeypatch.setenv("MINDTRACE_SCHEMA_DIR", str(missing))
    with pytest.raises(FileNotFoundError):
        default_schema_dir()
