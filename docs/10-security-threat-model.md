# 10 — Security & Privacy Threat Model

Status: **accepted (Phase 0)** · Expands: ADR-008 · Method: asset-centric + trust-boundary walk

---

## 1. Assets, ranked

| # | Asset | Why it matters |
|---|---|---|
| A1 | Raw memory prose, decision context, outcomes (per user) | The most sensitive data in the system: finances, relationships, regrets, health |
| A2 | Derived beliefs & traits (inferences the user never stated) | Sensitive *and* potentially wrong; leakage is a dignity harm, not just a privacy one |
| A3 | Per-user data encryption keys | Compromise ⇒ A1 fully exposed; destruction ⇒ A1 unrecoverable (that's a feature) |
| A4 | Auth credentials / session tokens | Account takeover ⇒ full A1+A2 access |
| A5 | The event log's integrity | If mutable, every guarantee in ADR-001/008 collapses |
| A6 | LLM provider request payloads | Egress of A1 fragments to a third party |
| A7 | Audit & model-run ledgers | Tampering hides misuse |

---

## 2. Trust boundaries

```
[ Browser / user ] --TLS--> [ API (FastAPI) ] --local--> [ engines (pure) ]
                                   |                          |
                                   |--> [ Postgres + RLS ] <--/  (ciphertext at rest)
                                   |--> [ Redis (broker only) ]
                                   |--> [ KMS / keyring ]   (wraps A3)
                                   \--> [ llm/ ] --TLS--> [ external LLM provider ]   <-- boundary of concern for A6
```

Boundary B1 user↔API, B2 API↔DB, B3 API↔KMS, **B4 llm/↔provider** (the only egress of user
content), B5 API↔worker (via Redis).

---

## 3. Threats and controls

### T1 — Malicious / adversarial memory content
*Vector:* user (or someone who compromised their account) stores memory text crafted to (a)
inject instructions into the LLM, (b) exploit a parser, (c) poison inferences.
*Controls:*
- **Injection containment (ADR-003 §guards):** memory text reaches the LLM only inside a
  delimited, labelled *data* block; the system prompt declares that block untrusted; output is
  schema-validated regardless; retrieval never concatenates memory text into an instruction slot.
- Output can only ever be categorical factor levels + a `rationale_span` bounded to the data
  block. It cannot carry a weight, a score, or a decision (ADR-003 rule 1).
- Storage is parameterised (SQLAlchemy), text is opaque `bytea`; no eval/templating of memory
  content anywhere.
- Inference poisoning is *bounded*: one memory contributes one bounded-weight `Evidence` edge;
  a single memory cannot dominate a trait; the user sees the trace and can dispute.
*Residual:* a very persuasive benign-looking memory can still bias a trait within the bounded
weight. Accepted; visible in the trace.

### T2 — Prompt injection reaching *other* users
*Not applicable by construction:* no cross-user data flow (ADR-005/008 — no pooling). An
injection can only affect the injecting user's own twin.

### T3 — Unauthorised memory / belief access
*Vector:* IDOR, a missing ownership check, a query bug.
*Controls:* (a) every repository method takes `user_id` and filters by it; (b) a service-layer
decorator asserts the principal owns the target → `404` on mismatch; (c) **Postgres RLS** keyed
on `SET app.user_id` per transaction, fail-closed (unset GUC ⇒ zero rows); (d) API tests fire
cross-tenant IDs at every route.
*Residual:* a bug that sets the wrong `app.user_id`. Mitigated by `db/session.py` centralising
the `SET` and a test that every session helper sets it.

### T4 — Inference leakage (A2)
*Vector:* an error message, a log line, an analytics event, or an over-broad API response
exposing a derived belief or its evidence prose.
*Controls:* problem+json errors carry no prose or belief values; `structlog` processors redact
known sensitive keys; `AuditLog.payload_hash` stores a hash, never the inputs; `evidence`
excerpts are decrypted only in the response to the owning user; no third-party analytics on
belief content.
*Residual:* embeddings are stored cleartext and are partially invertible. Documented; encrypting
them at rest is a v2 option.

### T5 — Deletion not honoured (A1/A2)
*Vector:* a "deleted" memory still influences a belief; a backup retains erased data.
*Controls:* deletion is an **event** honoured by the fold (ADR-001) + row removal + partial
re-derivation; `DeletionPlan` dry-run is tested to equal the applied effect; account erasure
**destroys the data key** (crypto-shred) so backups become ciphertext-without-key immediately,
then rows are hard-deleted; `tests/integration/test_deletion_rederivation.py` and
`test_erasure_leaves_nothing.py` are release gates.
*Residual:* data already sent to the LLM provider (see T7) cannot be retracted.

### T6 — Event-log tampering (A5/A7)
*Vector:* an operator or a bug mutates/deletes events or audit rows.
*Controls:* no `UPDATE`/`DELETE` code path to `memory_event`, `audit_log`, `model_run`,
`consent_record` (enforced: no ORM method, a DB role without those grants for the app user, a
test asserting attempts raise); per-user contiguous `seq` makes silent gaps detectable; optional
hardening (v2): hash-chain each event to its predecessor.
*Residual:* a DB superuser can still rewrite history. Out of scope for a portfolio deployment;
noted.

### T7 — LLM provider exposure (A6, boundary B4)
*Vector:* A1 fragments sent to `extract`/`verbalize` are retained, logged, or trained on by the
provider.
*Controls:* **only `mindtrace.llm` egresses** (import-linter enforced); it sends the *minimal
span* needed, runs a regex/NER redaction pass on obvious identifiers, sets provider
zero-retention where the provider offers it, and logs payload size + purpose to `ModelRun`;
**embeddings run locally** (`providers/local_embeddings.py`) so the highest-volume call never
leaves the box; `use_llm_provider = false` consent disables extraction/verbalisation entirely
(system degrades to manual structured entry).
*Residual:* redaction is imperfect; the provider is still trusted with redacted fragments during
processing. **Stated plainly in the README.**

### T8 — API abuse / DoS
*Vector:* credential stuffing, brute force, expensive-endpoint hammering (`/simulate`,
`/elicitation`), enumeration.
*Controls:* argon2id password hashing; per-IP + per-account rate limits (Redis counters) with
`Retry-After`; `/simulate` and self-consistency extraction gated per user per minute; generic
`404` (no existence oracle); `Idempotency-Key` prevents duplicate expensive work; request body
size caps; `extra="forbid"` on all request models.
*Residual:* a determined attacker with many IPs. Acceptable at this scale; a WAF/CDN is a
deployment-time add.

### T9 — Auth weaknesses (A4)
*Controls:* short-lived access tokens (~30 min) + rotating refresh tokens; refresh-token reuse
detection (revoke the family); tokens are `HttpOnly`+`Secure` cookies or bearer with a strict
CSP; logout revokes server-side; no password reset in v1 MVP (added with an email provider
later, out-of-band token).
*Residual:* no MFA in v1. Documented; MFA is a fast-follow.

### T10 — Key management (A3, boundary B3)
*Controls:* master key in a KMS (prod) / injected env var (dev), never in the DB or repo; the
DB stores only wrapped per-user data keys + a key ref; data keys are unwrapped into process
memory per request and not persisted; rotation re-wraps data keys without re-encrypting row
data.
*Residual:* a host compromise reads data keys from process memory while a request runs. Inherent
to "compute over plaintext"; noted.

---

## 4. What MINDTRACE guarantees — and does not

**Guarantees (testable):**
- Confidentiality of A1 at rest, given an uncompromised KMS.
- Per-user cryptographic isolation; erasure makes A1 unrecoverable immediately.
- Every inferred belief has a complete, queryable evidence chain and an audit row.
- Deleting a source exactly recomputes or removes everything derived from it.
- The event, audit, and model-run logs are append-only from the application.
- No user's data ever influences another user's twin.
- A truthful record of every LLM call: purpose, model, prompt version, payload size, outcome.

**Does NOT guarantee:**
- Protection of data *in use* (it is decrypted in app memory to compute and to call the LLM).
- Safety against a compromised master key, a malicious operator with DB+KMS access, or a host
  compromise during a request.
- Retraction of, or the provider's own deletion of, data already sent to the LLM provider.
- Non-invertibility of stored embeddings (treated as sensitive; cleartext at rest in v1).
- MFA, anomaly detection, or defence against a distributed application-layer DoS in v1.

These limits are in the README, not buried.

---

## 5. Security tests (map to `tests/api/`, `tests/integration/`)
`test_ownership_isolation` · `test_rls_fail_closed` · `test_prompt_injection` (corpus) ·
`test_error_responses_carry_no_prose` · `test_append_only_tables_reject_update` ·
`test_deletion_rederivation` · `test_erasure_leaves_nothing` · `test_rate_limit` ·
`test_refresh_token_reuse_revokes_family` · `test_llm_egress_only_from_llm_package`
(import-linter) · `test_consent_gate_blocks_inference`.
