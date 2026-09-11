"""Architecture invariant: layer 0/1 packages stay framework-independent.

Static (AST) check, independent of the import-linter config, so this test fails
the instant a forbidden import is *written* -- it does not need the package to
be importable with the forbidden dependency uninstalled, and it does not depend
on ``lint-imports`` being on PATH (see ``test_architecture_contracts.py`` for
that complementary check).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from uuid import uuid4

import pytest

# tests/unit/test_import_isolation.py -> parents[0]=unit, [1]=tests, [2]=backend
BACKEND_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = BACKEND_ROOT / "src" / "mindtrace"
DOMAIN_ROOT = SRC_ROOT / "domain"
EVENTS_ROOT = SRC_ROOT / "events"

FORBIDDEN_TOP_LEVEL = {
    "fastapi",
    "starlette",
    "sqlalchemy",
    "alembic",
    "redis",
    "arq",
    "anthropic",
    "openai",
    "langchain",
    "langchain_core",
    "httpx",
    "httpx2",
    "numpy",
}

ALL_MINDTRACE_SUBPACKAGES = {
    "mindtrace.api",
    "mindtrace.config",
    "mindtrace.domain",
    "mindtrace.events",
    "mindtrace.services",
    "mindtrace.engines",
    "mindtrace.llm",
    "mindtrace.db",
    "mindtrace.security",
    "mindtrace.observability",
    "mindtrace.workers",
}

# Each layer 0/1 package, its source root, and the OTHER mindtrace packages it
# may import (its own package is always implicitly allowed).
LAYERS: dict[str, tuple[Path, frozenset[str]]] = {
    "mindtrace.domain": (DOMAIN_ROOT, frozenset()),
    "mindtrace.events": (EVENTS_ROOT, frozenset({"mindtrace.domain"})),
}


def _source_files(root: Path) -> list[Path]:
    assert root.is_dir(), f"expected {root} to exist"
    return sorted(root.rglob("*.py"))


def _imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _cases() -> list[tuple[Path, str, frozenset[str]]]:
    return [
        (path, layer, allowed)
        for layer, (root, allowed) in LAYERS.items()
        for path in _source_files(root)
    ]


@pytest.mark.parametrize(
    ("path", "layer", "allowed"),
    _cases(),
    ids=lambda v: str(v.relative_to(SRC_ROOT)) if isinstance(v, Path) else str(v),
)
def test_layer_file_imports_no_forbidden_module(
    path: Path, layer: str, allowed: frozenset[str]
) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = _imported_modules(tree)
    forbidden_mindtrace = ALL_MINDTRACE_SUBPACKAGES - allowed - {layer}

    for module in imported:
        top_level = module.split(".")[0]
        rel = path.relative_to(SRC_ROOT.parent.parent)
        assert top_level not in FORBIDDEN_TOP_LEVEL, f"{rel} imports forbidden module {module!r}"
        for forbidden in forbidden_mindtrace:
            assert not module.startswith(forbidden), f"{rel} imports forbidden {module!r}"


def test_domain_package_is_importable_with_forbidden_modules_absent() -> None:
    """Belt-and-braces: prove the AST check by actually blanking sys.modules."""
    present = [name for name in FORBIDDEN_TOP_LEVEL if name in sys.modules]
    forbidden_present = {name: sys.modules.pop(name) for name in present}
    domain_modules = [name for name in sys.modules if name.startswith("mindtrace.domain")]
    for name in domain_modules:
        del sys.modules[name]
    try:
        from mindtrace import domain  # noqa: PLC0415

        bundle = domain.load_schema_bundle()
        assert bundle.schema_version == 1
    finally:
        sys.modules.update(forbidden_present)


def test_events_package_is_importable_with_forbidden_modules_absent() -> None:
    """Same guarantee for ``mindtrace.events``: importable with only ``domain`` present."""
    present = [name for name in FORBIDDEN_TOP_LEVEL if name in sys.modules]
    forbidden_present = {name: sys.modules.pop(name) for name in present}
    events_modules = [name for name in sys.modules if name.startswith("mindtrace.events")]
    for name in events_modules:
        del sys.modules[name]
    try:
        from mindtrace import events  # noqa: PLC0415
        from mindtrace.domain import UserId  # noqa: PLC0415

        store = events.InMemoryEventStore()
        assert store.read_stream(UserId(uuid4())) == ()
    finally:
        sys.modules.update(forbidden_present)
