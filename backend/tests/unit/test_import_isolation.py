"""Architecture invariant: the domain layer is framework-independent.

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

import pytest

# tests/unit/test_import_isolation.py -> parents[0]=unit, [1]=tests, [2]=backend
BACKEND_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = BACKEND_ROOT / "src" / "mindtrace"
DOMAIN_ROOT = SRC_ROOT / "domain"

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
FORBIDDEN_MINDTRACE_SUBPACKAGES = {
    "mindtrace.api",
    "mindtrace.config",
    "mindtrace.services",
    "mindtrace.engines",
    "mindtrace.events",
    "mindtrace.llm",
    "mindtrace.db",
    "mindtrace.security",
    "mindtrace.observability",
    "mindtrace.workers",
}


def _domain_source_files() -> list[Path]:
    assert DOMAIN_ROOT.is_dir(), f"expected {DOMAIN_ROOT} to exist"
    return sorted(DOMAIN_ROOT.rglob("*.py"))


def _imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize(
    "path", _domain_source_files(), ids=lambda p: str(p.relative_to(DOMAIN_ROOT))
)
def test_domain_file_imports_no_forbidden_module(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = _imported_modules(tree)

    for module in imported:
        top_level = module.split(".")[0]
        assert top_level not in FORBIDDEN_TOP_LEVEL, (
            f"{path.relative_to(DOMAIN_ROOT.parent.parent)} imports forbidden module {module!r}"
        )
        for forbidden in FORBIDDEN_MINDTRACE_SUBPACKAGES:
            assert not module.startswith(forbidden), (
                f"{path.relative_to(DOMAIN_ROOT.parent.parent)} imports forbidden {module!r}"
            )


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
