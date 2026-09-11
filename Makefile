# Convenience wrapper around the commands CI runs. Assumes a Windows dev venv
# at backend/.venv (see backend/README.md for the equivalent raw commands and
# the Linux/macOS venv path, used verbatim by .github/workflows/backend.yml).
.PHONY: install format lint typecheck imports test golden-update check

BACKEND := backend
PY := .venv/Scripts/python.exe

install:
	cd $(BACKEND) && python -m venv .venv
	cd $(BACKEND) && $(PY) -m pip install --upgrade pip
	cd $(BACKEND) && $(PY) -m pip install -e ".[dev]"

format:
	cd $(BACKEND) && $(PY) -m ruff format src tests

lint:
	cd $(BACKEND) && $(PY) -m ruff check src tests

typecheck:
	cd $(BACKEND) && $(PY) -m mypy

imports:
	cd $(BACKEND) && .venv/Scripts/lint-imports.exe --config .importlinter

test:
	cd $(BACKEND) && $(PY) -m pytest

golden-update:
	cd $(BACKEND) && MINDTRACE_GOLDEN_UPDATE=1 $(PY) -m pytest tests/golden -q

# Everything CI runs, in the same order.
check: lint typecheck imports test
