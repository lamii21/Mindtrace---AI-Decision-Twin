# 02 — Domain Model

Status: **accepted (Phase 0)** · Related: ADR-001 (event sourcing), ADR-008 (provenance)

This document defines the domain **conceptually**: aggregates, ownership, what is immutable, what
is a derived projection, relationships, and lifecycle. SQL comes later (milestone M2+); the
dossier §7 sketch is indicative, not binding.

---

## 1. The three tiers of state

MINDTRACE state divides cleanly into three tiers. Every entity belongs to exactly one.

| Tier | Definition | Entities | Rule |
|---|---|---|---|
| **A — Source of truth** | Append-only facts. Never updated, never hard-deleted (tombstoned by a *new* event). | `MemoryEvent`, `ConsentRecord`, `AuditLog`, `ModelRun` | Immutable. The system's memory *is* the ordered `MemoryEvent` stream per user. |
| **B — Materialised snapshots** | Immutable once written, but are checkpoints of something derivable. Kept for provenance and reproducibility even though tier C could be rebuilt. | `TwinVersion`, `Prediction`, `Simulation`, `Evidence` | Immutable. Stamped with `engine_version` + input hash. |
| **C — Projections** | Read models folded from tier A. Fully rebuildable by replay. Rebuilt on demand, on schedule, and after any deletion. | `Memory`, `Experience`, `Preference`, `Value`, `Trait` (current), `Contradiction` (open set) | May be truncated and recomputed at any time. Never authored directly by a user or an API call. |

`Decision`, `Outcome`, `Twin`, `Scenario`, `User` are **operational records** — mutable in
narrow, audited ways (see lifecycles below). They are not projections (you cannot rebuild them
from events) and not append-only.

---

## 2. Aggregates

An *aggregate* is a consistency + transaction boundary. Cross-aggregate references are by ID
only; cross-aggregate writes never share a transaction except where noted.

### AG-1 · User  *(aggregate root: `User`)*

Owns identity and the legal basis for processing.

- `User` — id (UUID), email, `password_hash` (argon2id), `status`, `created_at`, `data_key_ref`
  (pointer into the keyring, **not** the key), `deleted_at`.
- `ConsentRecord` — id, user_id, `scope` (`store_memories` / `run_inference` / `use_llm_provider`
  / `retain_outcomes`), `granted` (bool), `policy_version`, `at`. **Immutable**; a change of mind
  is a new row. Inference engines check the latest row for the relevant scope before running.

Ownership: `User` owns **everything** transitively. Every other table carries `user_id` and every
query is scoped by it (belt: application check; braces: Postgres RLS — ADR-008).

Lifecycle: `created` → (`active`) → `deletion_requested` → **erasure job**: all tier A/B/C rows
for the user removed or crypto-shredded (data key destroyed), `User` row retained as a tombstone
(id + `deleted_at` + hashed email) for audit-of-deletion only.

### AG-2 · MemoryLog  *(aggregate root: the per-user event stream)*

The heart of ADR-001.

- `MemoryEvent` — id, user_id, `seq` (per-user monotonic, gap-free), `type`
  (`ingested` / `corrected` / `deleted` / `elicitation_answered` / `outcome_recorded`),
  `payload` (AEAD ciphertext of a typed JSON body), `source`
  (`declared` / `observed` / `inferred`), `occurred_at` (when the real-world thing happened,
  user-supplied, nullable), `created_at` (when we recorded it), `causation_id` (the event that
  caused this one, nullable), `correlation_id` (request/session grouping).

Invariants: no `UPDATE`, no `DELETE`. `(user_id, seq)` unique and contiguous. A "deletion" is a
`deleted` event naming the target event id(s) or a topic selector; projectors honour it during
the fold. Append is the only write path into the system for user knowledge.

Lifecycle: events are `appended` and thereafter only `read`. Stream is unbounded; snapshots
(tier B `TwinVersion` and periodic projection snapshots) bound replay cost.

### AG-3 · MemoryProjection  *(root: `Memory`)*

- `Memory` — id, user_id, `type` (`episodic` / `semantic` / `preference` / `decision`),
  `text` (ciphertext), `embedding` (`vector(1024)`, cleartext — it is not human-readable prose),
  `source`, `confidence` (float, 1.0 for `declared`), `salience` (float, recency+importance),
  `valid_from`, `superseded_by` (self-FK), `deleted_at`, `origin_event_seq` (the event it was
  folded from), `projector_version`.
- `Experience` — id, `memory_id` (1:1, episodic subtype), `role`, `organisation`, `period_start`,
  `period_end`, `impact_note` (ciphertext). A typed lens over an episodic `Memory`, not an
  independent thing.

Rule: **never written by an API handler.** Only `MemoryProjector` writes here, and it may
`TRUNCATE ... WHERE user_id = ?` and rebuild. Anything a user "edits" about a memory becomes a
`corrected` event; the projection reflects it on the next fold.

### AG-4 · BeliefProjection  *(roots: `Preference`, `Value`; `Trait` belongs to AG-6)*

- `Preference` — id, user_id, `dimension` (a `FactorId` from `factors.yaml`), `value` ∈ [−1, 1],
  `importance` ∈ [0, 1], `confidence` ∈ [0, 1], `ci_low`, `ci_high`, `source`, `updated_at`,
  `projector_version`.
- `Value` — id, user_id, `label`, `polarity`, `confidence`, `abstract = true`. A higher-order
  preference; same evidence mechanics, coarser.

Rule: projections. Rebuilt by `PreferenceProjector` from `elicitation_answered` events +
observed decisions (via the Bayesian updater in `engines/preference/`). The current
`Preference` row is tier C; the *history* of how it moved is reconstructable from events and is
what the Evolution Engine reads.

### AG-5 · Decision  *(aggregate root: `Decision`)*

- `Decision` — id, user_id, `title`, `context` (ciphertext), `options` (JSONB: list of named
  option bodies), `extracted_factors` (JSONB: `{FactorId: level}` per option, produced by the
  LLM extractor, **schema-validated**, with an `extraction_id` linking to a `ModelRun`),
  `chosen_option` (nullable — set when the user commits or logs a past choice),
  `reasoning` (ciphertext, nullable), `decided_at` (nullable), `status`
  (`draft` / `simulated` / `committed` / `archived`), `created_at`.

Contained: the situation snapshot is *part of* the Decision aggregate and frozen once `status ≥
simulated`, so a later replay uses the exact inputs the twin saw.

Relationships (by ID): `Decision 1—* Prediction`, `Decision 1—* Simulation`,
`Decision 1—0..1 Outcome`, `Decision *—* Memory` **through** `Evidence`.

Lifecycle: `draft` (user assembling options) → `simulated` (≥1 `Simulation`/`Prediction`
exists; situation frozen) → `committed` (`chosen_option` + `decided_at` set) →
`archived`. A past decision logged retrospectively is created directly at `committed` with
`decided_at` in the past; the extractor still runs to populate `extracted_factors`, and the
event `type = ingested, source = observed`.

### AG-6 · Twin  *(aggregate root: `Twin`)*

- `Twin` — id, user_id, `name` (`"Primary"`, or a user label), `created_at`. Thin.
- `TwinVersion` — id, twin_id, `version` (int, monotonic), `trait_snapshot` (JSONB: full
  `Trait` set with value/confidence/CI/posterior params), `weights` (JSONB: `WeightVector` over
  `FactorId`), `reason` (`scheduled` / `post_elicitation` / `post_decision` / `manual` /
  `schema_migration`), `engine_version`, `factor_schema_version`, `created_at`.
- `Trait` — **not a table of its own in tier C**; the authoritative current traits live inside
  the latest `TwinVersion.trait_snapshot`. A convenience read-model view `current_trait` may be
  materialised for querying but is derived from the latest version.

Rationale: a "trait" only means something *relative to a twin version and a factor schema*.
Binding `Trait` to `TwinVersion` (tier B, immutable) is what makes Counterfactual Replay and the
Evolution timeline exact.

Lifecycle: `Twin` created once per user at onboarding. `TwinVersion` **appended** whenever the
Preference projection materially changes (delta test in `engines/evolution/`) or on the weekly
cron. Versions are never edited or deleted (except in a full user erasure).

### AG-7 · Simulation  *(aggregate root: `Simulation`)*

- `Scenario` — id, user_id, `horizon` (`now` / `1y`), `assumptions` (JSONB, user-authored
  deltas to factor levels or weights), `base_twin_version_id`. Referenced by, not owned by, a
  Simulation — the same Scenario can feed several.
- `Simulation` — id, user_id, `decision_id`, `scenario_id` (nullable), `twin_configs` (JSONB:
  the N `(label, WeightVector)` pairs actually run — e.g. Career/Safe/Dream/Future),
  `results` (JSONB: per config → `DecisionResult` with outcome, score, margin, contributions),
  `synthesis` (JSONB: recommendation, conflict axis, vote tally, ensemble disagreement),
  `model_confidence` (JSONB: the `Confidence` object + its inputs), `engine_version`,
  `created_at`. **Immutable** once written.

Relationship: a `Simulation` references one `Decision` and one-or-more `TwinVersion`s (by ID
inside `twin_configs`). Re-running produces a *new* `Simulation`.

### AG-8 · Prediction / Outcome  *(paired records under `Decision`)*

- `Prediction` — id, decision_id, twin_version_id, `predicted_decision`
  (`ACCEPT` / `REJECT` / `UNCERTAIN`), `predicted_confidence` (float), `credible_interval`
  (JSONB `{low, high}`), `factor_contributions` (JSONB), `margin` (float), `simulation_id`
  (the run it came from), `engine_version`, `created_at`. **Immutable.** This is the row the
  Evaluation Engine scores.
- `Outcome` — id, decision_id (1:1), `actual_choice`, `actual_result` (ciphertext, free text),
  `satisfaction` ∈ {−2,−1,0,1,2}, `recorded_at`, `superseded_by` (self-FK). Recording is via an
  `outcome_recorded` event; a later revision appends a new event and a new `Outcome` row with
  `superseded_by` set on the old one (so regret-learning sees the correction history).

The `Prediction ↔ Outcome` join keyed on `decision_id` is the entire empirical basis of the
Calibration Report Card. No prediction is ever back-edited to match an outcome (principle 15).

### AG-9 · Evidence  *(edge entity, its own lightweight aggregate)*

- `Evidence` — id, user_id, `belief_type` (`preference` / `trait` / `value` /
  `decision_factor` / `contradiction`), `belief_id`, `source_kind` (`memory` / `decision` /
  `elicitation_answer` / `outcome`), `source_id`, `weight` (float), `polarity`
  (`support` / `contradict`), `engine_version`, `created_at`. **Immutable.**

This is the provenance graph as a plain table. "Why do you believe this?" =
`SELECT … WHERE belief_type = ? AND belief_id = ?`. The deletion cascade =
`SELECT belief_id … WHERE source_id IN (removed memories)` → mark those beliefs dirty → recompute.
Depth is 2–3; a `WITH RECURSIVE` handles the transitive case (belief supported by a belief).
See ADR-004 for why this is not Neo4j.

### AG-10 · Contradiction  *(aggregate root: `Contradiction`)*

- `Contradiction` — id, user_id, `kind` (`stated_vs_observed` / `preference_drift`),
  `belief_type`, `belief_id`, `conflicting_source_kind`, `conflicting_source_id`,
  `confidence` (computed), `detected_at`, `status` (`open` / `confirmed` / `dismissed`),
  `user_response` (ciphertext, nullable), `resolved_at`, `engine_version`.

Semi-projection: the *open* set is recomputed by the contradiction worker, but once a user
answers ("yes my preference changed" / "no"), the `confirmed`/`dismissed` state and
`user_response` are durable operational state **and** are themselves emitted as `corrected`
events so they feed back into projections. Lifecycle: `open` → `confirmed` |`dismissed` →
(may re-open if new conflicting evidence and prior status was `dismissed`).

### Cross-cutting · AuditLog, ModelRun

Not aggregates — infrastructure ledgers, tier A, append-only.

- `AuditLog` — id, user_id, `actor` (`user:<id>` / `system:<engine>` / `worker:<task>`),
  `action` (`belief.derived` / `memory.deleted` / `memory.read` / `prediction.created` /
  `consent.changed` / …), `target_type`, `target_id`, `engine_version`, `payload_hash`
  (sha256 of the canonicalised input set — lets you prove *what* produced a belief without
  storing the prose), `at`.
- `ModelRun` — id, user_id, `purpose` (`extract_factors` / `verbalize_trace` /
  `paraphrase_generate` / `embed` / `judge`), `provider`, `model`, `prompt_version`,
  `prompt_hash`, `tokens_in`, `tokens_out`, `cost_usd`, `latency_ms`, `outcome`
  (`ok` / `validation_failed` / `provider_error` / `fell_back`), `at`.

---

## 3. Immutability summary

| Immutable (never `UPDATE`) | Mutable, narrowly + audited | Rebuildable projection (truncate + replay) |
|---|---|---|
| `MemoryEvent`, `ConsentRecord`, `AuditLog`, `ModelRun`, `TwinVersion`, `Prediction`, `Simulation`, `Evidence` | `User` (status, keys), `Twin` (name), `Decision` (status/choice until `committed`), `Outcome` (via supersede), `Contradiction` (status/response) | `Memory`, `Experience`, `Preference`, `Value`, `current_trait` view, open `Contradiction` candidates |

---

## 4. Relationship map (by ID; `*` = many)

```
User 1─* MemoryEvent          User 1─* ConsentRecord        User 1─1 Twin
User 1─* Decision             User 1─* Simulation           User 1─* Contradiction
User 1─* AuditLog / ModelRun

MemoryEvent  ──fold──▶  Memory 1─0..1 Experience
MemoryEvent (elicitation_answered) + Decision(observed)  ──update──▶  Preference / Value
Preference / Value / Trait   ◀─derives from─  Evidence  ─references─▶  Memory | Decision | Outcome | elicitation answer

Twin 1─* TwinVersion         TwinVersion ─contains─ Trait set + WeightVector
TwinVersion  ─referenced by─  Scenario, Simulation.twin_configs[], Prediction

Decision 1─* Simulation       Simulation ─produces─▶ Prediction (1 per twin_config, or 1 for the synthesis)
Decision 1─* Prediction       Decision 1─0..1 Outcome
Prediction ⇄ Outcome  (join on decision_id → Evaluation Engine)

Decision *─* Memory  THROUGH  Evidence (belief_type = decision_factor)
Contradiction ─references─▶ (belief_id) + (conflicting source)
```

---

## 5. Lifecycle: the two flows that define the system

### 5.1 Ingest → belief

1. `POST /memories` → `MemoryService.ingest` opens a txn.
2. Append `MemoryEvent(type=ingested, source=declared|observed)`. **This is the commit point** —
   if anything downstream fails, the fact is still safely recorded.
3. Enqueue projection (or run inline in M2): `MemoryProjector` folds the new event →
   upsert `Memory` (+ `Experience` if episodic), compute embedding via `llm.embed`.
4. If the memory is preference-bearing: `PreferenceProjector` calls
   `engines.preference.update` → new `Preference` value/CI → write `Evidence` edges →
   `AuditLog(action=belief.derived, payload_hash=…)`.
5. Delta check (`engines.evolution`): if traits moved materially → append a `TwinVersion`.

### 5.2 Simulate a decision

1. `POST /simulate {decision_id}` → `DecisionService.simulate` opens a txn.
2. Load frozen `Decision` situation + latest `TwinVersion`.
3. `llm.extract(context, FactorExtraction schema)` → validated `{FactorId: level}` per option;
   record `ModelRun`. On validation failure → deterministic fallback or `UNCERTAIN`.
4. `engines.mcda.decide(...)` per option → `DecisionResult` (outcome, score, margin,
   contributions). Pure. No LLM.
5. `engines.simulation.parallel(...)` runs Career/Safe/Dream/Future weight vectors → per-twin
   results + ensemble disagreement.
6. `engines.confidence.model_confidence(ConfidenceInputs(evidence_sufficiency, ensemble_disagreement,
   historical_calibration, extraction_entropy, margin))` → `Confidence` (value + CI). **Never the LLM.**
7. If `margin < MARGIN_MIN` or `confidence < C_MIN` → outcome forced to `UNCERTAIN`.
8. `engines.debate.synthesis(...)` → structured synthesis; optionally
   `engines.debate.verbalize(...)` → `llm.verbalize` with the constrained template + post-check.
9. Persist immutable `Simulation` + `Prediction`(s); write `Evidence(belief_type=decision_factor)`
   linking each contribution to the memories that set the relevant trait; `AuditLog`.
10. Return a response DTO assembled in `api/schemas` — never an ORM row.

---

## 6. What is deliberately NOT modelled in v1

- No `Trait` as an independently editable entity — it lives in `TwinVersion`.
- No shared/household twins, no twin-to-twin references.
- No graph database node/edge tables — `Evidence` + recursive CTE (ADR-004).
- No soft-delete on tier A — deletion is an *event*, erasure is crypto-shred.
- No separate "psychology" model — traits are MCDA weights with uncertainty, nothing more
  (ADR-005, and PHASE-0-REVIEW on why claiming more would be dishonest).
