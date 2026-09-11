# 08 — API Contracts

Status: **draft (Phase 0)** · Layer: `api/` (spec §01) · All bodies are Pydantic v2 models in `api/schemas/`

---

## 1. Conventions

| Concern | Rule |
|---|---|
| Base path | `/v1`. OpenAPI at `/openapi.json`; the frontend generates TS types from it (`frontend/lib/api/`). |
| Auth | `Authorization: Bearer <JWT>` on every route except `POST /v1/auth/register` and `POST /v1/auth/login`. Access token ~30 min; refresh via `POST /v1/auth/refresh`. |
| Ownership | Every resource is scoped to the authenticated user; a mismatch is `404` (not `403` — don't confirm existence). Enforced in `services/` + Postgres RLS (ADR-008). |
| Request validation | All request models `extra = "forbid"`, typed enums, field constraints. A violation → `422` with the problem+json `errors[]` array. |
| Errors | RFC 9457 `application/problem+json`: `{type, title, status, detail, instance, errors?}`. Domain-error → status map in `api/errors.py`. Never leak stack traces or decrypted prose in errors. |
| Idempotency | `Idempotency-Key` header honoured on `POST /v1/memories`, `POST /v1/decisions`, `POST /v1/simulate`, `POST /v1/predictions/{id}/outcome`. |
| Async work | Long operations return `202` + `{job_id}`; poll `GET /v1/jobs/{job_id}` → `{status, result_url?}`. Projection after `POST /memories` is synchronous in milestone M2, async (202) from M5. |
| Pagination | Opaque `cursor` + `limit` (default 25, max 100). Responses: `{items, next_cursor}`. |
| Time | All timestamps ISO-8601 UTC. Engines receive `now` explicitly; the API sets it. |
| Consent | Routes that trigger inference or an LLM call check `ConsentRecord`; missing scope → `409 consent_required` with the scope named. |

---

## 2. Auth

| Method & path | Request | Response |
|---|---|---|
| `POST /v1/auth/register` | `RegisterRequest{email: EmailStr, password: SecretStr(min 12)}` | `201 AuthUser{user_id, email, created_at}` |
| `POST /v1/auth/login` | `LoginRequest{email, password}` | `200 TokenPair{access_token, refresh_token, token_type="bearer", expires_in}` |
| `POST /v1/auth/refresh` | `RefreshRequest{refresh_token}` | `200 TokenPair` |
| `POST /v1/auth/logout` | — | `204` |
| `GET /v1/auth/me` | — | `200 MeResponse{user_id, email, created_at, consents: list[ConsentState]}` |
| `PUT /v1/auth/consent` | `ConsentUpdate{scope: ConsentScope, granted: bool}` | `200 ConsentState{scope, granted, policy_version, updated_at}` |
| `POST /v1/auth/account:delete` | `AccountDeleteRequest{confirm: Literal["DELETE"]}` | `202 {job_id}` — triggers crypto-shred + erasure (ADR-008) |
| `GET /v1/auth/account:export` | — | `202 {job_id}` → job result is a signed download of all user data as JSON |

`ConsentScope = store_memories | run_inference | use_llm_provider | retain_outcomes`.

---

## 3. Memories

| Method & path | Request | Response |
|---|---|---|
| `POST /v1/memories` | `MemoryCreate` | `202 MemoryAccepted{memory_event_id, projection: "pending"|"done", memory_id?}` |
| `GET /v1/memories` | query: `type?, source?, topic?, cursor?, limit?` | `200 Page[MemoryOut]` |
| `GET /v1/memories/{id}` | — | `200 MemoryOut` |
| `DELETE /v1/memories/{id}` | query: `dry_run: bool = true` | `dry_run` → `200 DeletionPlan`; else `202 {job_id}` |
| `POST /v1/memories:forget` | `ForgetRequest{topic: str, dry_run: bool = true}` | `200 DeletionPlan` or `202 {job_id}` |

```
MemoryCreate:
  kind: Literal["note","experience","decision_record","preference_statement"]
  text: str                       # 1..8000 chars; encrypted at rest
  source: Literal["declared","observed"]     # "inferred" is system-only
  occurred_at: datetime | None
  structured: dict | None          # optional pre-parsed fields (e.g. Experience.role/org/period)

MemoryOut:
  id: UUID
  type: Literal["episodic","semantic","preference","decision"]
  text: str
  source: Literal["declared","observed","inferred"]
  confidence: float
  occurred_at: datetime | None
  created_at: datetime
  origin_event_seq: int
  supports: list[BeliefRef]         # beliefs whose Evidence cites this memory
  superseded_by: UUID | None
  deleted_at: datetime | None

DeletionPlan:
  target_memory_ids: list[UUID]
  affected_beliefs: list[BeliefImpact]      # {belief_type, belief_id, label, change: "recompute"|"remove", before, after_estimate}
  affected_traits: list[TraitDelta]
  invalidated_predictions: int
  twin_version_will_bump: bool
  reversible: Literal[false]                # deletion is not reversible; the plan says so plainly
```

---

## 4. Decisions

| Method & path | Request | Response |
|---|---|---|
| `POST /v1/decisions` | `DecisionCreate` | `201 DecisionOut` |
| `GET /v1/decisions` | query: `category?, status?, cursor?` | `200 Page[DecisionSummary]` |
| `GET /v1/decisions/{id}` | — | `200 DecisionOut` |
| `PATCH /v1/decisions/{id}` | `DecisionPatch{chosen_option?, reasoning?, status?}` | `200 DecisionOut` — situation fields immutable once `status ≥ simulated` |
| `GET /v1/decisions/{id}/simulations` | — | `200 Page[SimulationSummary]` |

```
DecisionCreate:
  title: str
  category: Literal["career","education","project","purchase","relationship","other"]
  context: str                     # free text; encrypted; the extractor's input
  options: list[OptionIn]          # 1..6; a binary decision may send just the opportunity
  high_stakes: bool = false
  decided_at: datetime | None      # set (with chosen_option) to log a PAST decision
  chosen_option: str | None

OptionIn: {id: str, label: str, body: str}

DecisionOut:
  id: UUID
  title: str
  category: str
  context: str
  options: list[OptionIn]
  status: Literal["draft","simulated","committed","archived"]
  extracted_factors: dict[str, dict[FactorId, FactorReading]] | None   # per option; null until first simulate
  extraction_model_run_id: UUID | None
  chosen_option: str | None
  reasoning: str | None
  decided_at: datetime | None
  latest_prediction: PredictionSummary | None
  outcome: OutcomeOut | None
  created_at: datetime

FactorReading: {level: Literal["very_low","low","moderate","high","very_high"], known: bool, rationale_span: str}
```

---

## 5. Simulate

| Method & path | Request | Response |
|---|---|---|
| `POST /v1/simulate` | `SimulateRequest` | `200 SimulationOut` (also persists an immutable `Simulation` + `Prediction`) |
| `GET /v1/simulations/{id}` | — | `200 SimulationOut` |

```
SimulateRequest:
  decision_id: UUID
  twins: list[Literal["base","career","safe","dream","future"]] = ["base","career","safe","dream","future"]
  scenario_id: UUID | None          # conditional 1-year scenario (optional)

SimulationOut:
  simulation_id: UUID
  decision_id: UUID
  engine_version: str
  factor_schema_version: int
  twin_version_id: UUID
  decision:
    label: Literal["ACCEPT","REJECT","UNCERTAIN"]
    uncertain_reason: Literal["score_in_band","insufficient_coverage","low_model_confidence"] | None
    score: float                    # S, signed, [-1,1]
    margin: float
    coverage: float
  confidence: Confidence            # spec/06 s9 object, verbatim; NEVER equals abs(score)
  contributions: list[Contribution] # {factor_id, label, signed_pct, weight, n_value, direction}
  trace: TraceGraph                 # nodes+edges: decision <- factor <- evidence <- memory
  per_twin: list[TwinResult]        # {twin, label, score, top_contributions}
  synthesis:
    recommendation: Literal["ACCEPT","REJECT","UNCERTAIN"]
    label_consensus: Literal["unanimous","majority","split"]
    conflict_axis: list[FactorId]
    vote: dict[str, str]
  debate: list[DebateLine] | null   # constrained verbalisation (ADR-003 r4); null if post-check failed
  elicitation_hint: ElicitationHint | null   # present when uncertain_reason == "insufficient_coverage"

DebateLine: {twin: str, text: str, cites_factor: FactorId, cites_evidence_id: UUID}
ElicitationHint: {missing_factor: FactorId, question: str, expected_confidence_gain: float}
```

The response **must** carry `score` and `confidence.value` as separate fields; a contract test
asserts they are never wired to the same source (spec §06 §1).

---

## 6. Twins & evolution

| Method & path | Response |
|---|---|
| `GET /v1/twins` | `200 list[TwinSummary]` (usually one) |
| `GET /v1/twins/{id}` | `200 TwinOut{id, name, current_version, traits: list[TraitReport], updated_at}` |
| `GET /v1/twins/{id}/versions` | `200 Page[TwinVersionSummary]` |
| `GET /v1/twins/{id}/versions/{version}` | `200 TwinVersionOut{version, reason, trait_snapshot, weights, dispositions, engine_version, factor_schema_version, created_at}` |
| `GET /v1/twins/{id}/evolution?from={v}&to={v}` | `200 EvolutionDiff{deltas: list[TraitDelta], summary?: str}` — `summary` is optional LLM verbalisation, post-checked |

```
TraitReport:
  id: str                          # FactorId or disposition id
  kind: Literal["importance_weight","disposition"]
  value: float
  confidence: float                # per-trait learning indicator (spec/04 s5) - NOT model confidence
  credible_interval: {low: float, high: float}
  evidence_count: int
  source: Literal["declared","inferred"]
  trend: Literal["rising","falling","stable"] | None

TraitDelta: {id, kind, before, after, ci_before, ci_after, classification: Literal["new_preference","faded","reprioritised","confidence_shift","stable"], significant: bool}
```

---

## 7. Elicitation (Twin Interview)

| Method & path | Request | Response |
|---|---|---|
| `POST /v1/elicitation/sessions` | — | `201 ElicitationSession{session_id, progress, next_item: InterviewItemOut}` |
| `GET /v1/elicitation/sessions/{id}` | — | `200 ElicitationSession` |
| `POST /v1/elicitation/sessions/{id}/answers` | `ElicitationAnswer` | `200 ElicitationStep{accepted: bool, next_item: InterviewItemOut | None, progress, trait_preview: list[TraitReport]}` |
| `POST /v1/elicitation/sessions/{id}:finalize` | — | `200 {twin_id, twin_version_id, interview_noise}` (also allowed to auto-finalize when target reached) |

```
InterviewItemOut:
  item_id: str
  kind: Literal["likert","pairwise","gamble","intertemporal","ambiguity","effort"]
  prompt_a: str | None
  prompt_b: str | None
  prompt: str | None               # likert
ElicitationAnswer:
  item_id: str
  choice: Literal["A","B","indifferent"] | int   # int 1..5 for likert
  latency_ms: int | None
```

`trait_preview` lets the UI show the live-updating trait panel (spec §07). Server never sends the
factor profiles / design vectors to the client.

---

## 8. Evidence & disputes

| Method & path | Request | Response |
|---|---|---|
| `GET /v1/evidence/{belief_type}/{belief_id}` | — | `200 EvidenceChain` |
| `POST /v1/beliefs/{belief_type}/{belief_id}:dispute` | `DisputeRequest{reason: str, corrected_value: float | None}` | `202 {event_id, job_id}` — appends a `corrected` event, re-derives |

```
EvidenceChain:
  belief: {type, id, label, value, confidence, source}
  engine_version: str
  edges: list[EvidenceEdge]
EvidenceEdge:
  source_kind: Literal["memory","decision","elicitation_answer","outcome"]
  source_id: UUID
  source_excerpt: str              # short, decrypted server-side, ownership-checked
  weight: float
  polarity: Literal["support","contradict"]
  engine_version: str
  created_at: datetime
```

`belief_type ∈ {preference, trait, value, decision_factor, contradiction}`.

---

## 9. Predictions, outcomes, evaluation

| Method & path | Request | Response |
|---|---|---|
| `POST /v1/predictions/{id}/outcome` | `OutcomeCreate` | `201 OutcomeOut` |
| `PUT /v1/predictions/{id}/outcome` | `OutcomeCreate` | `200 OutcomeOut` (supersedes prior; both retained) |
| `GET /v1/evaluation/report-card` | query: `category?` | `200 ReportCard` |
| `GET /v1/evaluation/consistency` | — | `200 ConsistencyReport` |

```
OutcomeCreate:
  actual_choice: str               # option id or free label
  actual_result: str               # free text; encrypted
  satisfaction: int                # -2..2
  occurred_at: datetime

ReportCard:
  n_predictions_total: int
  n_resolved: int
  calibrated: bool
  gates: {min_for_accuracy: int, min_for_calibration: int, min_for_consistency: int}
  prediction_accuracy: MetricWithCI | null      # null until gate met -> UI shows "collecting (k/N)"
  brier_score: MetricWithCI | null
  expected_calibration_error: MetricWithCI | null
  reliability_bins: list[ReliabilityBin] | null
  by_category: dict[str, CategoryMetrics] | null
  disclaimer: str                  # fixed text: measures model-data consistency, not psychological truth

MetricWithCI: {value: float, ci_low: float, ci_high: float, n: int}
```

---

## 10. Contradictions

| Method & path | Request | Response |
|---|---|---|
| `GET /v1/contradictions` | query: `status?` (default `open`) | `200 Page[ContradictionOut]` |
| `POST /v1/contradictions/{id}:respond` | `ContradictionResponse{answer: Literal["changed","not_changed","dismiss"], note: str | None}` | `200 ContradictionOut` — also appends a `corrected` event |

```
ContradictionOut:
  id: UUID
  kind: Literal["stated_vs_observed","preference_drift"]
  belief: BeliefRef
  conflicting: {source_kind, source_id, excerpt}
  confidence: float
  detected_at: datetime
  status: Literal["open","confirmed","dismissed"]
  prompt: str                      # e.g. "Six months ago location was very important. This option is far away. Has that changed?"
```

---

## 11. Jobs

| `GET /v1/jobs/{job_id}` | `200 Job{id, kind, status: Literal["queued","running","succeeded","failed"], result_url?, error?, created_at, finished_at}` |

---

## 12. Status-code map (excerpt, `api/errors.py`)

| Domain error | HTTP |
|---|---|
| `NotOwner`, `ResourceNotFound` | `404` |
| `ValidationError` (Pydantic) | `422` |
| `ConsentRequired` | `409` + `detail` names the scope |
| `SituationFrozen` (PATCH after simulate) | `409` |
| `ExtractionUnavailable` (LLM down, no fallback path) | `503` — but `POST /simulate` still returns `200` with `UNCERTAIN / extraction_unavailable` where the fallback applies |
| `IdempotencyKeyConflict` | `409` |
| `RateLimited` | `429` + `Retry-After` |
