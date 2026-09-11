# ADR-001 — Event-sourced memory

Status: **accepted** · Date: 2026-09-09 · Deciders: lead AI SWE

## Context

MINDTRACE must satisfy several requirements that a conventional mutable-CRUD schema cannot
satisfy simultaneously:

- **Exact right-to-be-forgotten.** "Forget everything about location" must remove the source
  data *and* demonstrably undo every inference that depended on it — not best-effort.
- **Explainability over time.** For any belief the system must answer "which inputs, and which
  version of which engine, produced this, and when".
- **Reproducibility.** Re-running derivation on the same inputs must yield the same beliefs, so
  that a bug fix can be applied retroactively and audited.
- **Evolution.** The Evolution Engine needs the *history* of how a trait moved, not just its
  current value.

All four collapse to one property: **beliefs must be a deterministic projection of an ordered,
immutable log of user-provided facts.**

## Decision

The single write path for user knowledge is **append a `MemoryEvent`** to a per-user,
gap-free, monotonically-sequenced, append-only stream. Events are typed (`ingested`,
`corrected`, `deleted`, `elicitation_answered`, `outcome_recorded`) and carry an AEAD-encrypted
JSON payload.

All of `Memory`, `Experience`, `Preference`, `Value`, and the current trait set are **read
models** produced by deterministic projectors that fold the stream. They can be truncated and
rebuilt at any time. A "deletion" is a `deleted` event that projectors honour during the fold;
physical erasure is handled separately by crypto-shredding (ADR-008).

`TwinVersion` snapshots bound replay cost: replay starts from the last snapshot ≤ target seq.

We use a **hand-rolled minimal event store** (one table, an `append()` and a `read_stream()`),
not an event-sourcing framework.

## Alternatives considered

1. **Mutable CRUD + audit triggers.** Standard tables, Postgres triggers writing an audit table.
2. **Full CQRS/ES framework** (e.g. `eventsourcing` lib, Marten-style, Kafka as the log).
3. **Bitemporal tables** (`sys_period`, `valid_period`) without an explicit event concept.
4. **Soft-delete flags + recompute on demand**, no log.

## Why rejected

1. *Audit triggers* record that a row changed, not the causal input set that produced a derived
   belief, and give no clean "replay from scratch" story. Deletion still mutates in place, so
   proving downstream invalidation means trusting cascade code with no way to re-verify.
2. *A framework* imports a large conceptual surface (sagas, process managers, snapshotting
   policies, upcasting DSLs) for one aggregate that matters. It becomes the thing you explain in
   the interview instead of the decision intelligence. Violates engineering principle 10.
   Kafka adds an operational component with no payoff at single-user scale.
3. *Bitemporal only* preserves history but not intent — you cannot distinguish "user corrected
   a fact" from "projector overwrote a value", and topic-scoped deletion has no natural form.
4. *No log* makes reproducibility impossible: once a preference is overwritten you cannot
   reconstruct what it was derived from, so you cannot re-derive after a bug fix or a deletion.

## Consequences

**Positive**
- Deletion preview is literally a dry-run replay with the `deleted` event applied — trivially
  correct, testable (`tests/integration/test_deletion_cascade.py`).
- `rederive(user_id)` is a first-class operation; a `projector_version` bump triggers a
  scheduled rebuild for all users.
- Property test: fold(events) is pure and order-deterministic; replaying twice is byte-identical.

**Negative / costs**
- Every projector must be a pure fold with an explicit version. Discipline cost on every PR that
  touches derivation.
- Read models can lag writes; M2 runs projection inline (synchronous) to defer the eventual-
  consistency question until the worker exists.
- Schema changes to the event payload require an **upcaster** (`events/upcast.py`) mapping old
  payload versions forward at read time. This is accepted complexity and is bounded.
- Storage grows monotonically. Acceptable: a heavy user is O(10⁴) events; snapshots cap replay.

**Neutral**
- The event store interface is a Protocol in `events/`; the Postgres implementation is in `db/`.
  Swapping to another backing store later touches one file.
