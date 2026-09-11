# mindtrace (backend)

Python 3.12, FastAPI, Pydantic v2. Layered per
[`docs/architecture/01-repository-structure.md`](../docs/architecture/01-repository-structure.md);
`src/mindtrace/domain/` depends on nothing but the standard library and Pydantic
(enforced by `.importlinter` and `tests/unit/test_import_isolation.py`).

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\python -m pip install -e ".[dev]"
# Linux / macOS
.venv/bin/python -m pip install -e ".[dev]"
```

Or from the repo root: `make install`.

## Running checks

```bash
ruff check src tests          # lint
ruff format --check src tests # format check
mypy                           # type check
python -m importlinter --config .importlinter   # architecture boundaries
pytest                         # tests
```

Or `make check` from the repo root (runs the same four, in the same order as CI).

Regenerate the schema golden snapshot after a deliberate `schema/*.yaml` change:

```bash
MINDTRACE_GOLDEN_UPDATE=1 pytest tests/golden -q
```

## Running the API (M1: `/health` only)

```bash
uvicorn mindtrace.api.app:app --reload
```

## What exists today (M1)

- `mindtrace.domain` - the factor taxonomy, trait model, and Twin Interview bank:
  typed, frozen, loaded from `../schema/*.yaml`, cross-validated against each
  other and against their JSON Schemas.
- `mindtrace.config` - environment-driven settings (`MINDTRACE_*`).
- `mindtrace.api` - a FastAPI app exposing `GET /health` only.

Everything else (MCDA, Bayesian preference updating, the LLM boundary,
persistence, auth, workers, ...) is later milestones -
see [`docs/11-roadmap-milestones.md`](../docs/11-roadmap-milestones.md).
