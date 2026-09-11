# 01 — Repository Architecture

Status: **accepted (Phase 0)** · Supersedes: dossier §5 sketch · Related: ADR-002, ADR-003

---

## 1. Guiding idea

The dossier's `/backend /frontend /docs …` split is fine at the top level but says nothing about
the thing that actually matters: **the decision intelligence must not depend on the web
framework, the ORM, or the LLM SDK.**

So the backend is organised as a **strict layered hexagon** with a single allowed dependency
direction. The payoff is concrete and demonstrable in an interview:

> `engines/` (the MCDA math, the Bayesian updater, the confidence model, the evaluation
> metrics) imports **only** `domain/` + numpy/scipy. It has no import of `fastapi`,
> `sqlalchemy`, `anthropic`, `redis`, or `arq`. Its unit tests spin up no database and no
> HTTP server. You can paste an engine into a notebook and it runs.

This is enforced mechanically (see §5), not by good intentions.

---

## 2. Top-level layout

```
mindtrace/
├── backend/
│   ├── pyproject.toml            # uv/pip; ruff, mypy (strict), pytest config
│   ├── alembic.ini
│   ├── src/mindtrace/            # single importable package (src-layout)
│   ├── migrations/               # alembic versions only
│   └── tests/
├── frontend/
│   ├── package.json
│   ├── app/                      # Next.js App Router
│   ├── components/
│   ├── lib/
│   └── tests/
├── schema/                       # language-agnostic canonical specs, versioned
│   ├── factors.yaml
│   ├── traits.yaml
│   ├── interview.yaml
│   └── CHANGELOG.md
├── docs/
│   ├── adr/
│   ├── architecture/
│   ├── spec/
│   ├── api/
│   └── runbook/
├── notebooks/                    # exploration only — never imported by src/
├── infra/
│   ├── docker-compose.yml
│   ├── docker-compose.dev.yml
│   ├── backend.Dockerfile
│   ├── frontend.Dockerfile
│   └── postgres/init.sql
├── .github/workflows/
├── Makefile
└── README.md
```

---

## 3. Backend package (`backend/src/mindtrace/`)

Layers are listed **in dependency order**: each layer may import the ones above it and nothing
below it.

```
domain/        →  (numpy, pydantic only)          layer 0  — pure
engines/       →  domain                           layer 1  — deterministic intelligence
events/        →  domain                           layer 1  — event types + replay logic
llm/           →  domain                           layer 1  — provider boundary
db/            →  domain                           layer 1  — persistence
security/      →  domain                           layer 1  — auth, keys
observability/ →  domain                           layer 1  — logging, tracing, run records
services/      →  domain, engines, events, llm, db, security, observability   layer 2
api/           →  services, domain (+ api/schemas)                            layer 3
workers/       →  services                                                    layer 3
config.py      →  (pydantic-settings)              layer 0
```

### `domain/` — layer 0, pure

| Responsibility | The shared vocabulary: value objects, enums, typed IDs, the in-memory shape of every concept, domain errors. Loads `schema/*.yaml` into frozen typed objects. |
|---|---|
| Belongs here | `FactorId`, `TraitId`, `EpistemicSource` enum (`declared/observed/inferred/uncertain`), `DecisionOutcome` enum, `Polarity` enum, `FactorSpec`, `TraitSpec`, `FactorVector`, `WeightVector`, `Contribution`, `CredibleInterval`, `EvidenceRef`, domain exceptions. Frozen dataclasses / `pydantic.BaseModel(frozen=True)`. |
| Must NOT contain | Any `import sqlalchemy`, `import fastapi`, `import anthropic`, `import redis`. No I/O. No `datetime.now()` inside pure functions (time is injected). No database IDs leaking in as `int` — use typed UUID wrappers. |

### `engines/` — layer 1, the reason the project exists

```
engines/
├── mcda/          normalize.py, aggregate.py, decide.py, sensitivity.py
├── preference/    prior.py, update.py, posterior.py         (Bayesian trait estimation)
├── confidence/    model_confidence.py                       (NOT decision score)
├── evidence/      retrieve.py, provenance.py, rank.py
├── memory/        classify.py (calls llm boundary via injected port), dedup.py
├── simulation/    parallel.py, scenario.py
├── debate/        disagreement.py, synthesis.py, verbalize.py (verbalize = orchestrates llm port)
├── contradiction/ stated_vs_observed.py, drift.py
├── evolution/     snapshot_diff.py, classify_delta.py
└── evaluation/    brier.py, calibration.py, reliability.py, consistency.py
```

| Responsibility | Every decision-critical computation. Deterministic. Pure functions where possible; where an engine needs the LLM or retrieval it receives a **port** (Protocol) as an argument — it never imports `llm/` or `db/` directly. |
|---|---|
| Belongs here | Pure math. `decide(factor_vector, weight_vector, config) -> DecisionResult`. `update_posterior(prior, observation) -> Posterior`. `model_confidence(inputs: ConfidenceInputs) -> Confidence`. Golden-testable, property-testable. Given identical inputs + `engine_version`, identical output — always. |
| Must NOT contain | Database access, HTTP, transaction management, `anthropic` import, prompt strings, wall-clock reads, un-seeded RNG, logging side effects that change behaviour. **No LLM call that returns a value used in a calculation.** The LLM may only be invoked to produce text for humans or to produce a structured object that is then schema-validated *before* entering the engine. |

### `events/` — layer 1, event sourcing

| Responsibility | Define the event types, the append-only store interface, the projectors that fold events into read models, and the re-derivation entrypoint. |
|---|---|
| Belongs here | `MemoryEventType` enum (`ingested/corrected/deleted/elicitation_answered`), `Event` frozen model, `EventStore` Protocol (`append`, `read_stream`, `read_all_since`), `Projector` base, concrete projectors (`MemoryProjector`, `PreferenceProjector`), `rederive(user_id, from_seq=0)` orchestration, `DeletionPlan` (dry-run of a tombstone's downstream effect). |
| Must NOT contain | The concrete SQL implementation of `EventStore` (that lives in `db/`). Business rules about *what* a decision means. Anything that mutates an event after append. |

### `llm/` — layer 1, the ONLY provider boundary

```
llm/
├── ports.py          # Protocols: Extractor, Embedder, Verbalizer, Judge   (imported by engines/services)
├── client.py         # concrete implementation wiring the protocols to a provider
├── contracts/        # Pydantic models for EVERY structured LLM output
├── prompts/          # versioned templates: extract_factors.v1.txt, verbalize_trace.v1.txt
├── guards.py         # input sanitisation (injection), output validation, retry, deterministic fallback
└── providers/
    ├── anthropic.py        # the single file importing the anthropic SDK
    └── local_embeddings.py # self-hosted bge-m3 / e5
```

| Responsibility | Contain *all* knowledge of prompts, providers, tokens, and model IDs. Expose four narrow, typed functions. Every output crosses back into the app as a validated Pydantic instance or raises. |
|---|---|
| Belongs here | `extract(text, schema) -> schema instance`, `embed(texts) -> list[vector]`, `verbalize(structured, template) -> str`, `judge(pair) -> JudgeVerdict`. Prompt-injection defences. `model_run` emission. Provider retry/fallback. Prompt version pinning. |
| Must NOT contain | Any decision logic. Any code that decides `ACCEPT`/`REJECT`. Any confidence computation. Reading or writing domain tables directly (it takes/returns plain objects; persistence is the caller's job). Business rules. |

### `db/` — layer 1, persistence

```
db/
├── base.py           # DeclarativeBase, naming conventions
├── session.py        # engine, sessionmaker, get_session
├── models/           # ORM classes — mirror the domain but ARE NOT the domain
├── repositories/     # the only code that writes SQL / query expressions
├── crypto.py         # SQLAlchemy TypeDecorator for field-level AEAD (encrypt on bind, decrypt on result)
└── event_store.py    # concrete EventStore backed by the `memory_event` table
```

| Responsibility | Map domain objects to Postgres and back. House the repositories (query objects). Implement `EventStore`. Implement encrypted column types. |
|---|---|
| Belongs here | `MemoryModel`, `DecisionModel`, `PredictionModel`, …; `MemoryRepository`, `EvidenceRepository`; recursive-CTE queries for the provenance graph; pgvector similarity queries; Alembic-visible metadata. |
| Must NOT contain | Business rules (no "if margin < X return UNCERTAIN" here). MCDA. Confidence. Anything importing `engines/`. FastAPI. Prompt text. ORM models must not be returned past `services/` — routers see Pydantic DTOs, not ORM rows. |

### `security/` — layer 1

| Responsibility | Authentication (argon2 password hashing, JWT/session issuance), authorization (per-user ownership checks), per-user encryption key lifecycle, Postgres row-level-security policy definitions. |
|---|---|
| Belongs here | `hash_password`, `verify_password`, `issue_token`, `current_user` dependency helper (the FastAPI wiring is thin and lives in `api/deps.py`), `Keyring` (fetch/rotate per-user data keys from KMS or env-backed master key), RLS policy SQL. |
| Must NOT contain | Domain logic. Direct engine calls. |

### `observability/` — layer 1

| Responsibility | `structlog` configuration, OpenTelemetry tracer/span helpers, and the writers for the two append-only accountability tables: `audit_log` and `model_run`. |
|---|---|
| Belongs here | `configure_logging()`, `tracer`, `@traced` decorator that tags a span with the input memory-set hash, `record_audit(actor, action, target, engine_version, payload_hash)`, `record_model_run(...)`. |
| Must NOT contain | Anything that changes computation results based on whether tracing is on. |

### `services/` — layer 2, use-case orchestration

| Responsibility | One class/module per use case. Owns the **transaction boundary**. Loads inputs via repositories, calls engines with pure data, persists results, writes audit + model-run records, returns domain objects (never ORM rows). |
|---|---|
| Belongs here | `MemoryService.ingest(...)`, `MemoryService.delete(...)` (builds `DeletionPlan`, applies, re-derives), `DecisionService.simulate(...)` (extract → MCDA → parallel twins → confidence → verbalize → persist prediction), `ElicitationService.answer(...)`, `EvaluationService.recompute(...)`. |
| Must NOT contain | Math (delegate to engines). Prompt text (delegate to `llm/`). HTTP concerns (status codes, headers). SQL (delegate to repositories). |

### `api/` — layer 3

```
api/
├── app.py            # FastAPI() factory, middleware, exception handlers, OpenAPI export
├── deps.py           # DI: get_session, current_user, service factories
├── errors.py         # domain error -> HTTP mapping
├── schemas/          # request/response DTOs — Pydantic, versioned, NEVER the domain or ORM types
└── routers/          # auth.py, memories.py, decisions.py, simulate.py, twins.py,
                      # elicitation.py, evidence.py, predictions.py
```

| Responsibility | HTTP only: parse/validate request DTOs, call one service, serialise the result DTO, map errors to status codes. Export `openapi.json` for the frontend type generator. |
|---|---|
| Must NOT contain | Business logic, math, multi-step orchestration, direct repository or engine calls, direct LLM calls. A router method should be ~5–15 lines. |

### `workers/` — layer 3

| Responsibility | `arq` task registration + cron schedule. Each task is a thin wrapper that calls a service. |
|---|---|
| Belongs here | `tasks/contradiction_scan.py`, `tasks/evolution_snapshot.py`, `tasks/evaluation_recompute.py`, `tasks/embedding_backfill.py`, `WorkerSettings` with cron. |
| Must NOT contain | Business logic. If a task grows logic, that logic moves into a service and the task keeps calling it. |

---

## 4. Tests (`backend/tests/`)

```
tests/
├── unit/          per-engine, no DB, no network. Fast (<2s whole folder target).
├── property/      hypothesis: MCDA monotonicity, score bounds, posterior sanity, idempotent replay.
├── golden/        frozen input → frozen expected output. data/ holds JSON fixtures incl. the
│                  5 hand-worked MCDA examples from spec §05. A diff = a deliberate review.
├── integration/   real Postgres (testcontainers), repositories, event replay, deletion cascade.
├── api/           httpx against the ASGI app, auth, ownership, schema validation, injection payloads.
└── evaluation/    the metric code checked against reference implementations; consistency-probe
                   reproducibility on a fixed synthetic twin.
```

`tests/` mirrors `src/mindtrace/` one-to-one for `unit/`. Shared fixtures in `tests/conftest.py`
and `tests/factories/` (deterministic object builders, seeded).

---

## 5. Enforced dependency rules

1. **import-linter** contract in `pyproject.toml`:
   - `domain` may not import any other `mindtrace.*` layer.
   - `engines` may import only `mindtrace.domain`.
   - `anthropic` / `openai` / any provider SDK may be imported **only** under `mindtrace.llm.providers`.
   - `sqlalchemy` may be imported **only** under `mindtrace.db`.
   - `fastapi` may be imported **only** under `mindtrace.api`.
   CI fails on violation.
2. **ruff** rule banning `datetime.now` / `datetime.utcnow` outside `mindtrace.observability` and
   `mindtrace.api` — engines receive `now: datetime` as a parameter.
3. **mypy --strict** on `domain/`, `engines/`, `events/`, `llm/contracts/`.
4. A unit test asserts `engines/` is importable with `sqlalchemy`, `fastapi`, `anthropic` absent
   from `sys.modules` (import isolation guard).
5. Every engine module exposes `ENGINE_VERSION: str`; a test asserts each derived-row writer
   stamps it.

---

## 6. Frontend (`frontend/`)

```
frontend/
├── app/
│   ├── (dashboard)/          Twin Overview
│   ├── simulate/             Decision Simulator + trace
│   ├── parallel/             Parallel YOU + debate
│   ├── evolution/            version timeline
│   ├── reportcard/           calibration / model card
│   ├── memory/               browser + deletion preview
│   └── interview/            Twin Interview
├── components/
│   ├── trace/                the right-to-left evidence graph (visx)
│   ├── confidence/           ring + credible-interval band
│   └── primitives/           tokens, evidence chip, epistemic-source badge
├── lib/
│   ├── api/                  generated types from openapi.json + typed fetch client + TanStack hooks
│   └── viz/                  D3/visx helpers
└── tests/                    vitest + testing-library; Playwright smoke in e2e/
```

| Must NOT contain | Any re-implementation of decision logic (no computing confidence or contributions in JS — it renders what the API returns). Business thresholds. Secrets. |

---

## 7. `schema/` — canonical, language-agnostic, versioned from commit 1

`factors.yaml`, `traits.yaml`, `interview.yaml` are the single source of truth for the taxonomy.
Backend loads them at import into frozen `domain` objects; a test validates them against a JSON
Schema; `schema/CHANGELOG.md` + a `version:` field track every change. A migration is required
whenever a factor is added/removed/rescaled (see ADR-002 consequences).

## 8. `notebooks/`

Exploration, calibration studies, the MCDA prototype that produced spec §05. **Never imported by
`src/`.** CI runs `nbstripout --verify` so committed notebooks carry no output blobs. A notebook
may `import mindtrace.engines` but nothing in `src/` may `import` a notebook.

## 9. `infra/` and CI

`docker-compose.dev.yml` brings up Postgres+pgvector, Redis, the API (reload), the arq worker,
and the Next dev server. `.github/workflows/backend.yml`: ruff → mypy → import-linter →
pytest (unit+property) → pytest (integration, testcontainers) → coverage gate 80% on
`engines/` and `events/`, 70% overall. `frontend.yml`: eslint → tsc → vitest → build.
