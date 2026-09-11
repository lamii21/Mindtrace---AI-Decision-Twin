"""Locating the canonical ``schema/`` directory.

This is the one I/O seam the domain layer owns: resolving where the versioned,
version-controlled schema files live. It performs no parsing and no validation.
Pure calculations elsewhere in :mod:`mindtrace.domain` never call this.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_VAR = "MINDTRACE_SCHEMA_DIR"


def default_schema_dir() -> Path:
    """Return the repository ``schema/`` directory.

    Resolution order:

    1. the ``MINDTRACE_SCHEMA_DIR`` environment variable, if set;
    2. otherwise the ``schema/`` directory found by walking up from this file
       (``backend/src/mindtrace/domain/paths.py`` -> repo root -> ``schema``).

    Raises:
        FileNotFoundError: if neither location contains a directory.
    """
    override = os.environ.get(_ENV_VAR)
    if override:
        path = Path(override).expanduser().resolve()
        if not path.is_dir():
            msg = f"{_ENV_VAR}={override!r} does not point to a directory"
            raise FileNotFoundError(msg)
        return path

    for parent in Path(__file__).resolve().parents:
        candidate = parent / "schema"
        if candidate.is_dir():
            return candidate

    msg = (
        "could not locate a 'schema/' directory above "
        f"{Path(__file__).resolve()}; set {_ENV_VAR} to override"
    )
    raise FileNotFoundError(msg)
