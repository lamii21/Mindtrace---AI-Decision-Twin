"""Runs ``lint-imports`` (import-linter) against ``backend/.importlinter`` as a test.

Complements the AST-based ``test_import_isolation.py``: import-linter checks the
*installed, resolvable* dependency graph (transitive imports included), not just
the literal ``import`` statements in ``domain/``. Skipped if the binary can't be
found so a bare ``pytest`` (without the dev extras) still runs; CI and any dev
venv with ``[dev]`` installed always have it.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _find_lint_imports() -> str | None:
    """Locate the ``lint-imports`` console script.

    ``shutil.which`` alone misses it when the venv is not "activated" (its
    Scripts/bin directory absent from PATH) even though the interpreter running
    this test is that venv's own - so also check next to ``sys.executable``,
    where pip always places console scripts for the environment that owns them.
    """
    found = shutil.which("lint-imports")
    if found:
        return found
    exe_name = "lint-imports.exe" if sys.platform == "win32" else "lint-imports"
    candidate = Path(sys.executable).parent / exe_name
    return str(candidate) if candidate.is_file() else None


LINT_IMPORTS = _find_lint_imports()

pytestmark = pytest.mark.skipif(LINT_IMPORTS is None, reason="import-linter is not installed")


def test_import_linter_contracts_pass() -> None:
    assert LINT_IMPORTS is not None  # narrows for mypy; guaranteed by pytestmark's skip
    result = subprocess.run(
        [LINT_IMPORTS, "--config", str(BACKEND_ROOT / ".importlinter")],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"import-linter failed:\n{result.stdout}\n{result.stderr}"
