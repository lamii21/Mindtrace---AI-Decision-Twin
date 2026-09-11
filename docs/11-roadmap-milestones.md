# 11 — Development Roadmap: the first 10 milestones

Status: **accepted (Phase 0)** · Principle: milestones small enough to implement **and test** in
one focused session; each one leaves `main` green and demoable.

Legend — **Diff**: 🟢 small · 🟡 medium · 🔴 large-for-one-session (split if it slips).

> **Sequencing note (added after M2).** M1 pulled the minimal FastAPI `/health` app
> forward from the original M6 slot (harmless, infra-free; see M1's final report). M2 was
> re-scoped from "MCDA engine" to "event-sourced memory + evidence + provenance foundation" —
> the event-sourcing half of the original M4, built with an in-memory `EventStore`/
> `EvidenceStore` and **no PostgreSQL**, per ADR-001 and the M2 review below. The original M2
> (MCDA) and M3 (Bayesian preference) content is renumbered to **M3** and **M4** below, unchanged
> otherwise. PostgreSQL/Alembic/RLS (the rest of the original M4) is **deferred and unscheduled**
> — it lands whenever a later milestone first needs real durability, using the exact
> `EventStore`/`EvidenceStore` ports M2 already defines (swap the in-memory adapter, touch
> nothing above it). Milestones M5+ below predate this resequencing; treat their file lists as
> intent, not a contract, and re-verify against the ports actually in place when each is picked up
> — the same way this document is now being corrected against M1's and M2's real output.

---

## M1 — Repo skeleton + domain layer 🟢

**Objective.** `mindtrace` package installs and imports; `domain/` exposes enums, typed IDs, and
frozen `FactorSpec`/`TraitSpec` loaded from `schema/*.yaml`; CI (ruff, mypy --strict,
import-linter, pytest) is green.

**Files created.** `backend/pyproject.toml`, `backend/src/mindtrace/__init__.py`, `config.py`,
`domain/{__init__,ids,enums,factors,traits,errors}.py`, `schema/factors.schema.json`,
`schema/traits.schema.json`, `schema/CHANGELOG.md`, `tests/unit/domain/test_factor_loader.py`,
`tests/unit/domain/test_trait_loader.py`, `tests/unit/test_import_isolation.py`,
`.github/workflows/backend.yml`, `Makefile`, `infra/docker-compose.dev.yml` (postgres+redis),
`.importlinter`, `ruff.toml`.

**Files modified.** none.

**Dependencies.** stack base only (`pydantic`, `pyyaml`, dev: `ruff`, `mypy`, `pytest`,
`import-linter`, `hypothesis`).

**Tests.** YAML loads & validates against JSON Schema; 16 core factors present; anchors strictly
increasing; `direction` ∈ {benefit,cost}; every enum round-trips; **import isolation** —
`import mindtrace.domain` works with `sqlalchemy`/`fastapi`/`anthropic` absent from `sys.modules`.

**Acceptance.** `make test lint typecheck` green in CI; `import-linter` passes; a broken
`factors.yaml` (missing key) fails the loader test with a clear message.

---

## M2 — Event-sourced memory + evidence + provenance foundation 🔴 — **done**

**Objective.** The append-only source of truth and its first projection, in-memory only
(PostgreSQL deferred — see the sequencing note above): typed events for `ingested`/`corrected`/
`deleted` (ADR-001), a pure `fold_memory_events` projector, the `Memory`/`Evidence` domain types,
a source→epistemic-state classifier, and a deletion preview/apply built only from what M2 has.

**Created.** `domain/{memory,evidence,provenance}.py`; `domain/enums.py` +
`MemoryType`/`BeliefType`/`EvidenceSourceKind`; `domain/ids.py` + `UserId`/`EventId`/`MemoryId`/
`EvidenceId`; `events/{__init__,enums,types,store,in_memory_store,evidence_store,rederive}.py`;
`events/projectors/{__init__,memory}.py`; `tests/support/memory_fixtures.py`; `tests/unit/domain/
test_{memory_model,evidence_model,provenance}.py`; `tests/unit/events/test_{event_types,
in_memory_store,evidence_store,memory_projector,rederive,determinism}.py`;
`tests/property/test_event_properties.py`.

**Modified.** `domain/__init__.py` (exports), `.importlinter` (`events` layer + contracts),
`tests/unit/test_import_isolation.py` (parametrised over `domain/` and `events/`).

**Dependencies.** none new (stdlib `uuid`/`datetime` + already-present `pydantic`).

**Tests.** 229 passed. Append-only semantics (gap-free per-user `seq`, correction/deletion as new
events, no mutation/removal method on either store); provenance for all three `ProvenanceSource`
values + the `None → UNCERTAIN` case; exact e1→e2→e3 replay state; determinism (repeat fold
equal, immune to poisoned wall-clock/env/RNG); rebuildability (`rederive` after discard matches a
manual fold); fold-time integrity checks (conflicting `user_id`, duplicate/missing `seq`,
correcting/deleting a non-live memory); a deletion preview/apply cycle against `Evidence`; a
Hypothesis-generated valid event program (ingest/correct/delete respecting liveness) replays
deterministically; JSON round-trips for every event payload type. 98.98% coverage.

**Acceptance.** `lint-imports` 5/5 contracts kept; `ruff`/`ruff format`/`mypy --strict` clean; no
`engines/`, `db/`, `llm/`, `services/`, `security/`, `observability/`, or `workers/` directory
exists yet. See `docs/PHASE-0-REVIEW.md` for the M2 addendum and open questions this raised.

---

## M3 — MCDA engine (pure) 🟡

**Objective.** `engines/mcda/` implements spec §05 exactly; the 5 worked examples pass as golden
tests; all 9 properties pass.

**Created.** `engines/__init__.py`, `engines/mcda/{__init__,normalize,aggregate,decide,config}.py`,
`domain/decision.py` (`FactorReading`, `FactorVector`, `WeightVector`, `Contribution`,
`DecisionResult`), `tests/golden/data/mcda_examples/{1..5}.json`,
`tests/golden/test_mcda_golden.py`, `tests/property/test_mcda.py`,
`tests/property/test_determinism.py`, `notebooks/mcda_prototype.ipynb`.

**Modified.** `domain/__init__.py` (exports), `Makefile` (`golden-regen` target).

**Dependencies.** `numpy`.

**Tests.** golden 1–5 exact to 1e-6 (`S`, `label`, `uncertain_reason`, `coverage`, `margin`,
each `c_i%`); properties 1–9 (spec §05 §10) via `hypothesis` (≥ 500 examples); determinism
byte-equality across processes; `risk_tolerance = effort_tolerance = 0.5 ⇒ γ = 1`.

**Acceptance.** `pytest tests/golden tests/property -k mcda` green with `sqlalchemy` uninstalled;
`ENGINE_VERSION` present and asserted; the notebook reproduces every golden file.

---

## M4 — Bayesian preference engine (pure) 🟡

**Objective.** `engines/preference/` — build prior from `traits.yaml`, Laplace update for
pairwise observations, conjugate Beta update for dispositions, posterior read
(`value`/`confidence`/`credible_interval`).

**Created.** `engines/preference/{__init__,prior,update,posterior,config}.py`,
`domain/traits.py` extensions (`Posterior`, `TraitReport`), `tests/unit/preference/*`,
`tests/property/test_preference.py`.

**Modified.** `domain/__init__.py`.

**Dependencies.** `scipy`.

**Tests.** Laplace on Gaussian likelihood == analytic conjugate (`atol 1e-8`); single Beta
update == closed form; monotone-evidence property; `σ` floor; mean-zero gauge after every
update; synthetic-`θ*` recovery within 90% CI on covered directions; determinism.

**Acceptance.** recovery test green; property suite green; runs with no DB/network.

---

## PostgreSQL persistence — deferred, unscheduled

The original M4 also covered a Postgres-backed `EventStore` (Alembic baseline, RLS,
`db/event_store.py`). That work is **not dropped, just not yet scheduled**: M2 already defines
the `EventStore`/`EvidenceStore` ports a Postgres adapter would implement, so this becomes a
milestone of its own whenever a later step first needs real durability — swap the in-memory
adapter for a Postgres one, no change above the port. `M5`–`M10` below assume that milestone has
happened by the time each needs it (e.g. `M6`'s `db/session.py`, `M9`'s `migrations/`); re-verify
that assumption against what actually exists when each is picked up, per the sequencing note above.

---

## M5 — LLM boundary + factor extraction + fallback 🟡

**Objective.** `llm/` package: ports, Pydantic contracts, `extract()` with strict validation,
injection guards, `ModelRun` recording, the documented deterministic fallback. One real provider
adapter + a fake.

**Created.** `llm/{__init__,ports,client,guards}.py`, `llm/contracts/factor_extraction.py`,
`llm/prompts/extract_factors.v1.txt`, `llm/providers/{__init__,anthropic,fake}.py`,
`observability/model_run.py`, `db/models/model_run.py`, `migrations/0002_model_run.py`,
`tests/unit/llm/{test_contract_validation,test_guards,test_fallback}.py`,
`tests/api/test_prompt_injection.py` (corpus fixture).

**Modified.** `.importlinter` (provider-SDK contract), `config.py` (provider settings).

**Dependencies.** the chosen provider SDK, a local embedding model dep (`sentence-transformers`
or an ONNX runtime) — embeddings stubbed with a hash-based fake until M-later if needed.

**Tests.** malformed / extra-key / bad-enum output → `ExtractionValidationError` → fallback (all
`known=false`); injection corpus (~30 payloads) yields schema-valid-or-fallback output with no
echoed instructions and `rationale_span` confined to the data block; `ModelRun` row per call
incl. failures; import-linter confirms the provider SDK is only under `llm/providers`.

**Acceptance.** `engines/` + `tests/unit` still run with no network (fake injected); a live
smoke test (marked, not in the fast lane) does one real extraction.

---

## M6 — API skeleton: auth + memories + decisions CRUD 🔴

**Objective.** FastAPI app, JWT auth, `/v1/auth/*`, `/v1/memories` (create → event → **sync**
projection), `/v1/decisions` CRUD, problem+json errors, ownership + RLS wiring, OpenAPI export.

**Created.** `api/{app,deps,errors}.py`, `api/schemas/{auth,memory,decision,common,problem}.py`,
`api/routers/{auth,memories,decisions}.py`, `services/{memory_service,decision_service}.py`,
`security/auth.py`, `tests/api/{test_auth,test_memories,test_decisions,test_ownership,
test_openapi_snapshot}.py`.

**Modified.** `db/session.py` (per-request `SET app.user_id`), `conftest.py` (`client` fixture).

**Dependencies.** `fastapi`, `uvicorn`, `httpx`, `pyjwt`, `argon2-cffi`, `pydantic-settings`.

**Tests.** register→login→me→refresh; create memory → event appended → projection row visible in
`GET`; cross-tenant id → `404`; `extra` field → `422` problem+json; `/openapi.json` matches a
checked-in snapshot; error bodies carry no prose.

**Acceptance.** the API suite is green against real Postgres + fake LLM; a memory created via
HTTP is retrievable and its `origin_event_seq` is set.

---

## M7 — `simulate` end-to-end (base twin) + Prediction + trace 🔴

**Objective.** `POST /v1/simulate`: extract → MCDA → confidence (base twin only; ensemble term
fixed with the degenerate guard) → persist **immutable** `Simulation` + `Prediction` → build
`TraceGraph` + `Evidence(decision_factor)` edges → response DTO with **distinct** `score` and
`confidence`.

**Created.** `engines/confidence/{__init__,model_confidence,config}.py`,
`engines/evidence/{__init__,provenance,retrieve}.py`, `db/models/{simulation,prediction,evidence}.py`,
`migrations/0003_simulation.py`, `api/routers/simulate.py`, `api/schemas/simulation.py`,
`tests/unit/confidence/*`, `tests/golden/data/confidence_examples/{1..5}.json`,
`tests/api/{test_simulate,test_score_confidence_distinct}.py`.

**Modified.** `services/decision_service.py`, `observability/` (span per engine call).

**Dependencies.** none new.

**Tests.** golden `Confidence` for MCDA examples 1–5; `C ≠ abs(S)` contract; `UNCERTAIN` gates
fire for band + coverage; `Prediction` row rejects `UPDATE`; every trace edge resolves to a real
memory / elicitation answer; numeric path deterministic with the fake extractor pinned.

**Acceptance.** create decision → simulate → inspect trace works via HTTP; re-running simulate
creates a *new* `Simulation`, never mutates the old.

---

## M8 — Twin Interview (fixed order) + Twin / TwinVersion 🟡

**Objective.** `/v1/elicitation/*`; load `interview.yaml`; fixed prefix + fixed suffix;
per-answer `trait_preview`; `:finalize` → create `Twin` + first `TwinVersion` via the preference
engine; emit `elicitation_answered` events; write `Evidence` edges.

**Created.** `domain/interview.py`, `engines/elicitation/{__init__,session,select_fixed,finalize}.py`,
`db/models/{twin,twin_version}.py`, `events/projectors/preference.py`,
`migrations/0004_twin.py`, `api/routers/elicitation.py`, `api/schemas/elicitation.py`,
`services/elicitation_service.py`, `tests/unit/elicitation/*`,
`tests/integration/test_interview_to_twin.py`.

**Modified.** `services/decision_service.py` (use the real twin's weights, not a stub).

**Dependencies.** none new.

**Tests.** synthetic-user recovery through the API; **reproducibility** — same answer log →
byte-identical first `TwinVersion`; replaying the `elicitation_answered` events reproduces it;
contradictory `p03`/`p03r` raises `interview_noise` and lowers trait confidence.

**Acceptance.** a user completes the interview over HTTP and the resulting twin's weights change
a subsequent `/simulate` result in the expected direction.

---

## M9 — Deletion + re-derivation + Evidence API + dispute 🔴

**Objective.** `DELETE /v1/memories/{id}?dry_run`, `POST /v1/memories:forget`, `DeletionPlan`
builder, partial re-derivation keyed by `Evidence`, `GET /v1/evidence/{type}/{id}`,
`POST /v1/beliefs/{type}/{id}:dispute`, `AuditLog` writes on every derivation.

**Created.** `events/deletion_plan.py`, `observability/audit.py`, `db/models/audit_log.py`,
`migrations/0005_audit.py`, `api/routers/evidence.py`, `api/schemas/evidence.py`,
`engines/preference/recompute.py` (partial), `tests/integration/{test_deletion_cascade,
test_deletion_rederivation,test_dispute,test_audit_on_derivation}.py`.

**Modified.** `services/memory_service.py`, `events/rederive.py`.

**Dependencies.** none new.

**Tests.** dry-run `DeletionPlan` == applied effect; delete a memory supporting trait `T` → `T`
equals a full `rederive()` with that memory tombstoned; deleting the last support removes the
preference row; `dispute` writes a correction event, re-derives deterministically, and the
correction shows as a high-weight `Evidence` edge; an `AuditLog` row per belief write with a
stable `payload_hash`.

**Acceptance.** "forget everything about `location`" runs end-to-end with an accurate preview and
leaves an audit trail; no orphaned beliefs.

---

## M10 — Parallel twins + synthesis + ensemble confidence + workers + observability 🔴

**Objective.** `engines/simulation/parallel.py` + `schema/twins.yaml`; synthesis
(vote + conflict axis); wire `ensemble_disagreement` into confidence (+ degenerate guard);
structured `debate` object (verbalisation optional, post-checked); `arq` worker skeleton
(contradiction-scan + evolution-snapshot stubs on cron); `structlog` + OTel spans; `audit_log`
everywhere it isn't yet.

**Created.** `schema/twins.yaml`, `engines/simulation/{__init__,parallel,scenario}.py`,
`engines/debate/{__init__,disagreement,synthesis,verbalize}.py`,
`workers/{main,settings}.py`, `workers/tasks/{contradiction_scan,evolution_snapshot}.py`,
`observability/{logging,tracing}.py`, `llm/contracts/debate_line.py`,
`llm/prompts/verbalize_debate.v1.txt`, `tests/property/test_parallel_twins.py`,
`tests/unit/{simulation,debate}/*`, `tests/integration/test_audit_log.py`,
`tests/api/test_debate_postcheck.py`.

**Modified.** `api/schemas/simulation.py`, `services/decision_service.py`,
`engines/confidence/model_confidence.py`, `docker-compose.dev.yml` (worker service).

**Dependencies.** `arq`, `structlog`, `opentelemetry-sdk`.

**Tests.** parallel twins are distinct and user-anchored (`Career You` of a stability-lover is
still stability-leaning); `ensemble_disagreement` monotone in `λ`; `conflict_axis` matches a
hand-computed variance; degenerate guard caps the ensemble term; `debate` post-check rejects an
unknown evidence id / a sign mismatch and the API returns `debate: null`; an `AuditLog` row per
derivation; a cron task runs in a test harness.

**Acceptance.** `/simulate` returns per-twin results + synthesis + a real ensemble confidence
term; the worker process starts and executes a scheduled stub; every belief-writing path emits
an audit row.

---

## After M10 (Phase 2+, not detailed here)

Contradiction Engine (full), Evolution Engine (delta classification + timeline API),
Evaluation Engine (Report Card, Consistency Probe, regret), Active Elicitation (adaptive EIG
selector), "What would flip this?", Counterfactual Replay, the frontend build, async projection
cutover, production deployment + backup/restore drill + GDPR export/erasure jobs. Sequencing
follows the dossier's Phase 4–8; each becomes its own milestone list when its phase starts.
