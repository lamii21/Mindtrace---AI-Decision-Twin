# ADR-008 — Privacy and provenance

Status: **accepted** · Date: 2026-09-09 · Related: ADR-001, ADR-003, ADR-004

## Context

MINDTRACE holds an unusually sensitive corpus: a person's decisions, regrets, constraints,
relationships, finances, ambitions — plus *inferences* about them they never stated. The dossier
commits to encryption, access control, deletion, memory deletion, audit logs, consent,
explainability, and user control over inferred traits. These must be designed in from milestone
1, not bolted on, because several (exact deletion, re-derivable inference) constrain the core
architecture.

## Decision

### Provenance (the "why do you believe this" guarantee)

1. **Every derived belief writes `Evidence` edges** in the same transaction that writes the
   belief: `(belief_type, belief_id) → (source_kind, source_id, weight, polarity,
   engine_version)`. No belief exists without at least one edge (DB check + service assertion).
2. **Every derivation writes an `AuditLog` row**: `action=belief.derived`, `engine_version`,
   `payload_hash` = SHA-256 of the canonicalised input set (sorted memory ids + their content
   hashes + config hash). This lets us later *prove* what produced a belief without retaining
   the prose in the log.
3. **`source` epistemic tag** (`declared`/`observed`/`inferred`/`uncertain`) is a column on
   every belief and memory, surfaced in the API and rendered distinctly in the UI. An inferred
   value is never returned without an evidence route (API includes `evidence_url`; component
   tests enforce the chip).
4. **User correction is evidence.** "I disagree with this inference" appends a `corrected`
   event; the correction becomes a high-weight `Evidence` edge with `polarity=contradict` (or a
   pin), and the belief is recomputed with it applied. The disagreement is itself auditable.

### Privacy

5. **Field-level encryption at rest.** Prose columns (`memory.text`, `decision.context`,
   `decision.reasoning`, `outcome.actual_result`, `experience.impact_note`, event payloads,
   contradiction responses) are AEAD-encrypted (XChaCha20-Poly1305 or AES-GCM) with a
   **per-user data key**. Data keys are wrapped by a master key held in a KMS (prod) or an
   env-injected key (dev); the DB stores only ciphertext + a key reference. Embeddings and
   derived numbers are stored cleartext (needed for function; not human-readable prose).
6. **Crypto-shredding = deletion.** Account erasure destroys the user's data key → all
   ciphertext is unrecoverable immediately, and a background job then hard-deletes rows. Topic
   deletion uses the ADR-001 event mechanism + row removal + re-derivation, not crypto-shred.
7. **Access control, defence in depth.** (a) Application: every repository method takes
   `user_id` and filters by it; a decorator asserts the authenticated principal owns the target.
   (b) Database: Postgres **row-level security** policies keyed on a `SET app.user_id` per
   transaction, so a query bug cannot cross tenants. (c) No admin "view as user" in v1.
8. **Consent gating.** `ConsentRecord` scopes (`store_memories`, `run_inference`,
   `use_llm_provider`, `retain_outcomes`). Engines check the latest relevant scope before
   running; `use_llm_provider = false` disables extraction/verbalisation (system degrades to
   manual structured entry) rather than silently sending data out.
9. **LLM provider exposure is explicit and minimised.** Only `mindtrace.llm` egresses data
   (ADR-003). It sends the *minimal span* needed (not whole memories), runs a regex/NER
   redaction pass on obvious identifiers, sets provider zero-retention where offered, and logs
   every call to `ModelRun`. Embeddings run **locally** (`providers/local_embeddings.py`) so the
   highest-volume call never leaves the box. The README states plainly what still does.
10. **Audit of access, not just derivation.** Reads of decrypted prose by a system component are
    logged (`action=memory.read`) so "what has the system looked at" is answerable.

### What MINDTRACE can and cannot guarantee — stated honestly in the README

**Can:** at-rest confidentiality of prose given an uncompromised KMS; exact undo of an inference
when its source is deleted; a complete provenance chain for every inferred belief; tenant
isolation at two layers; immediate cryptographic unrecoverability on account deletion; a
truthful record of every LLM call and its payload size.

**Cannot:** protect data in use (it is decrypted in application memory to compute); prevent a
compromised master key / host from reading everything; retract data already sent to an LLM
provider; guarantee the hosted provider's own deletion; defend against a malicious operator with
DB + KMS access; make embeddings non-invertible (treated as sensitive, encrypted at rest is a
v2 option). These limits are documented, not hidden.

## Alternatives considered

1. **Full-database encryption only** (Postgres TDE / disk encryption), no field-level.
2. **Application-transparent column encryption with one global key.**
3. **Client-side / end-to-end encryption** (keys never on the server).
4. **Provenance as JSON blobs** on each belief instead of an `Evidence` table.
5. **Deletion = soft-delete flag**, rely on filters.

## Why rejected

1. Disk/TDE encryption protects only stolen disks, not a running DB, a dump, or a leaked
   backup with the key alongside. Insufficient for the sensitivity level.
2. One global key means one compromise exposes every user and defeats crypto-shred per user.
   Per-user keys are a small amount of extra machinery for a large isolation gain.
3. True E2E would be excellent for confidentiality but breaks the product: the server must
   compute over plaintext to derive beliefs and call the LLM. Incompatible with the core
   function; noted as an aspiration for a future "local-only" mode.
4. JSON blobs can't be queried for the deletion cascade or the "why" endpoint without scanning
   every belief; no referential integrity; `engine_version` per edge is awkward. The table is
   the right shape (ADR-004).
5. Soft-delete leaves the prose recoverable and the inferences intact — it fails the product's
   central privacy promise. Deletion must be real (event + row removal + re-derivation, or
   crypto-shred).

## Consequences

**Positive**
- Deletion, explanation, and correction are all expressible as operations on the same
  `event log + Evidence + AuditLog` substrate — one mechanism, heavily tested.
- `tests/integration/test_erasure.py` (no rows survive, key destroyed) and
  `test_deletion_rederivation.py` (dependent beliefs change/vanish) are acceptance gates.
- Clear story for an interview on a genuinely hard topic.

**Negative / costs**
- Per-user key management (wrap/unwrap, rotation, caching in memory for a request) is real
  code and a real operational concern; encapsulated in `security/keyring.py`.
- Encrypted columns are not indexable/searchable — search is via embeddings + metadata only.
- RLS + `SET app.user_id` requires every DB session to set the GUC; a missed set = queries
  return nothing (fail-closed) — annoying but safe. Enforced in `db/session.py`.
- Redaction before LLM calls is imperfect (NER misses); mitigated by minimal-span sending and
  documented as a residual risk.
