# 09 — Testing Strategy

Status: **accepted (Phase 0)** · Related: ADR-002, ADR-005, ADR-006 · Layout: [`01-repository-structure.md`](architecture/01-repository-structure.md) §4

Guiding rule (principle 14): **a core engine is not "done" until its tests are.** For
`engines/` and `events/`, tests are written from the spec *before* the implementation is
considered complete, and the coverage gate is 80%.

---

## 1. The pyramid

| Tier | Count target | Speed | Infra | What it proves |
|---|---|---|---|---|
| **Unit** | ~60% of tests | whole tier < 5 s | none (no DB, no network) | each pure function does what the spec says |
| **Property-based** (`hypothesis`) | ~10% | < 20 s | none | invariants hold over generated inputs, not just examples |
| **Golden** | ~10% | < 5 s | none | frozen input → frozen output; a diff = a deliberate review |
| **Integration** | ~12% | < 90 s | real Postgres (`testcontainers`) | event store, projections, repositories, RLS, deletion cascade |
| **API** | ~6% | < 60 s | ASGI app + Postgres + **fake** LLM | auth, ownership, validation, status codes, contracts |
| **Evaluation** | ~2% | < 30 s | none | metric code matches reference implementations; probes reproducible |

No end-to-end browser tests in the backend suite; the frontend has a small Playwright smoke
(`frontend/tests/e2e/`).

---

## 2. Determinism — the property the whole design rests on

`tests/property/test_determinism.py` and per-engine determinism tests assert:

1. **Byte-identical outputs.** `engine(inputs, ENGINE_VERSION)` serialised (canonical JSON, sorted
   keys, `float` repr pinned) is identical across: two calls in one process, two processes, and
   the Linux CI runner vs a developer machine (a recorded fixture from CI is checked in).
2. **No ambient inputs.** A test monkeypatches `time`, `random`, `os.environ`, and numpy's global
   RNG to poisoned values and asserts engine outputs are unchanged.
3. **Import isolation.** `tests/unit/test_import_isolation.py` removes `sqlalchemy`, `fastapi`,
   `anthropic` from `sys.modules`, then `import mindtrace.engines` and runs the MCDA golden
   suite — must pass.
4. **Replay equivalence.** `fold(events)` twice → identical projection rows; `rederive()` after a
   no-op event → identical beliefs.
5. **Seeded Monte Carlo** (confidence credible interval, spec §06 §6): fixed seed → identical
   interval bounds.

LLM calls are explicitly **exempt** from byte-determinism (providers drift) — which is safe
*only because* no reproducibility-critical value depends on them (ADR-003 rule 1). A test
(`test_llm_outputs_never_feed_math.py`) statically checks that `engines/` never imports
`mindtrace.llm.client` and that `Contribution`/`Confidence`/`DecisionResult` construction sites
take no argument sourced from an `llm.*` return.

---

## 3. What each hard area is tested for

### MCDA (`tests/golden/test_mcda_golden.py`, `tests/property/test_mcda.py`)
- Golden: the 5 worked examples from spec §05 §9 — exact `S`, `label`, `uncertain_reason`,
  `coverage`, `margin`, and every `c_i%` to 1e-6.
- Properties (spec §05 §10): bounds; `Σc_i = S`; monotonicity (benefit ↑ ⇒ `S` not ↓; cost ↑ ⇒
  `S` not ↑); factor-order invariance; dead-zone ⇒ `UNCERTAIN`; coverage gate dominance;
  neutral disposition ⇒ `γ = 1`; empty known set ⇒ no `ZeroDivisionError`.

### Preference posteriors (`tests/unit/preference/`, `tests/property/test_preference.py`)
- Laplace step on a Gaussian likelihood **equals** the analytic conjugate posterior (`atol 1e-8`).
- Single `Beta` disposition update **equals** the closed form.
- Monotone evidence: an answer favouring factor *i* never lowers `μ_i`.
- `σ` floor holds; posteriors never collapse below the floor before `N_eff` crosses the gate.
- Gauge: `Σ μ_i = 0` after every update.
- Synthetic recovery: draw `θ*`, generate noiseless answers to the full item bank, assert `μ`
  within the 90% CI of `θ*` on covered directions and all covered `σ` < `σ_prior`.

### Confidence (`tests/unit/confidence/`, golden)
- Each input function: extreme values + monotonicity (see spec §06 §10).
- `historical_calibration` shrink schedule; term **omitted** at `n = 0` and weights renormalise.
- Degenerate-twin guard caps the ensemble term.
- **`C` never equals `abs(S)`** across the golden set; DTO sign/type contract
  (`tests/api/test_score_confidence_distinct.py`).
- Golden `Confidence` object (incl. `inputs`) for MCDA examples 1–5.

### Evidence & provenance (`tests/integration/`)
- Every derived belief write creates ≥ 1 `Evidence` edge in the **same transaction** (rollback
  test: fail the belief write → no edge, no audit row).
- `GET /evidence/...` returns every edge; excerpts are ownership-checked and decrypted
  server-side only.
- `AuditLog` row per derivation with a stable `payload_hash` (same inputs → same hash).

### Deletion / re-derivation (`tests/integration/test_deletion_*.py`)
- `DeletionPlan` (dry-run) predicts exactly the beliefs that change/vanish when applied.
- Deleting a memory that supports trait `T` → `T` recomputes to the value obtained by a full
  `rederive()` with that memory's events tombstoned (two paths, same result).
- Deleting the *last* support for a preference → the preference row is removed, not left stale.
- A `dispute` correction event re-derives deterministically and the correction appears as a
  high-weight `Evidence` edge.
- Account erasure: no rows for the user survive; the data key is destroyed
  (`test_erasure_leaves_nothing.py`).

### LLM boundary (`tests/unit/llm/`, `tests/api/test_prompt_injection.py`)
- Malformed / extra-key / wrong-enum extraction output → `ExtractionValidationError` → the
  documented deterministic fallback (all `known=false` → coverage 0 → `UNCERTAIN`).
- Injection corpus (≈ 30 payloads: "ignore previous instructions", fake tool calls, base64,
  homoglyphs, "SYSTEM:" prefixes embedded in a memory) fired through `POST /memories` and into
  a simulate: assert (a) extraction output still schema-valid or falls back, (b) no output field
  contains instruction-shaped text echoed from the payload, (c) `rationale_span` stays within
  the provided data block.
- `ModelRun` row written for every call incl. failures (`outcome` set correctly).
- Engine suites use `llm/providers/fake.py` — a test asserts no real provider import is
  reachable from `tests/unit/`.

### Reproducibility (cross-cutting)
- `test_rederive_matches_live.py`: build a twin through the API (interview + N decisions), snapshot
  every belief, run a full `rederive()` from seq 0, assert identical.
- `test_golden_regen.py`: a `make golden-regen` target re-emits every golden file from the
  prototype notebook path; CI runs it in `--check` mode so a golden can't silently drift.

---

## 4. Fixtures, factories, fakes

- `tests/factories/` — deterministic builders (`make_twin(seed=…)`, `make_decision(...)`,
  `make_interview_answers(theta_star, noise=0)`), no randomness without an explicit seed.
- `tests/conftest.py` — `pg` (session-scoped testcontainer), `client` (ASGI + `pg` + fake LLM),
  `frozen_now` (fixed `datetime`), `poisoned_ambient` (breaks `time`/`random`/env).
- `llm/providers/fake.py` — returns canned, schema-valid extractions keyed by input hash;
  a `FakeExtractor(mode="malformed"|"drifting"|"slow")` for the failure-path tests.

---

## 5. Coverage gates & CI (`.github/workflows/backend.yml`)

```
ruff  ->  mypy --strict (domain, engines, events, llm/contracts)  ->  import-linter
      ->  pytest -m "unit or property or golden"        (fast, no infra)
      ->  pytest -m "integration or api"                (testcontainers)
      ->  coverage: fail under 80% on mindtrace/engines and mindtrace/events,
                    fail under 70% overall
      ->  pytest tests/golden --golden-check            (no silent drift)
```

Frontend: `eslint -> tsc --noEmit -> vitest -> next build -> playwright (smoke)`.

---

## 6. Explicitly NOT covered by automated tests (documented, done manually / later)
- LLM *quality* of extraction and verbalisation — needs a hand-labelled eval set (Phase 1
  deliverable, see PHASE-0-REVIEW); the schema-validity of its output *is* tested.
- Real provider latency / cost regressions — observed via `ModelRun` dashboards, not asserted.
- Visual regression of the trace/debate graphs — manual review + Playwright screenshot on demand.
- Load / concurrency beyond "one user's full history" — a single locust script in `infra/`,
  run before the production milestone, not in CI.
