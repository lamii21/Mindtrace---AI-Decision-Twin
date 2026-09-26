# ADR-009 — Encryption-at-rest key management and envelope

Status: **accepted** · Date: 2026-09-26 · Related: ADR-001, ADR-004, ADR-008

## Context

ADR-008 commits to field-level AEAD encryption with per-user keys "designed in from milestone 1,
not bolted on." The roadmap's concrete M6 entry (`docs/11-roadmap-milestones.md`) — the first
milestone that writes any prose column to a real database — lists a file/dependency set that
does not mention `security/keyring.py`, `db/crypto.py`, or any encrypted column type. Read
literally, that gap could be mistaken for permission to ship M6 with plaintext prose columns and
"add encryption later." This ADR closes that gap before `migrations/0001_*.py` is written: it
picks one concrete AEAD construction, defines the per-user key hierarchy ADR-008 only sketched,
and settles where the encryption boundary lives in the layered architecture — because a
`SQLAlchemy TypeDecorator`, ADR-004's original proposal, cannot safely resolve a *per-user* key
without smuggling request context through global/thread-local state, which every other part of
this architecture goes out of its way to avoid (engines take `now` as a parameter rather than
reading the wall clock; `events/` takes an `EventStore` Protocol rather than importing `db/`).

## Decision

**Encrypt from the first production-capable persistence migration (M6). No plaintext-then-migrate
path.** Rationale in "Why rejected" below.

### Cryptographic envelope

AEAD = **AES-256-GCM** via the `cryptography` library
(`cryptography.hazmat.primitives.ciphers.aead.AESGCM`) — the concrete pick from the pair ADR-008
already named ("XChaCha20-Poly1305 or AES-GCM"). `cryptography` is already the de facto standard
Python AEAD library, ships AES-NI–accelerated AES-GCM, and needs no second crypto dependency
(PyNaCl, which would be required for XChaCha20-Poly1305's extended nonce, adds a libsodium
binding for no benefit at MINDTRACE's realistic per-user scale — ADR-001 already estimates a
heavy user at O(10⁴) events, far below the ~2³² message birthday bound a random 96-bit GCM nonce
tolerates per key).

Per encrypted value:

```
format_version : 1 byte   (starts at 1)
key_version     : 4 bytes big-endian  (which user DEK generation encrypted this value)
nonce           : 12 bytes            (os.urandom, unique per encryption call)
ciphertext      : variable            (AESGCM output, tag appended per RFC 5116)
```

Stored as one `BYTEA` per sensitive column — one envelope, not split nonce/ciphertext/tag
columns, so a row is never partially readable and repository code stays a single
encrypt-in/decrypt-out call.

AAD (Associated Authenticated Data, not secret, but authenticated) =
`SHA-256(f"{table}.{column}:{user_id}:{row_id}")`. Binding table, column, user, and row into the
AAD means ciphertext from one cell can never be swapped into another cell (of the same user, same
table, same column, different row) and have it decrypt successfully — a real substitution risk
for fixed-shape rows without this binding.

### Per-user key hierarchy

```
master key (root)                      KMS (prod) / MINDTRACE_MASTER_KEY env var (dev, CI)
      │ wraps (AES-256-GCM)
      ▼
per-user DEK (32 random bytes, generated once at registration)
      │ encrypts (AES-256-GCM, envelope above)
      ▼
user sensitive content (memory_event.payload, memory.content, decision.{title,context,options,reasoning})
```

- The database **never stores a raw DEK** — only `wrapped_dek` (the DEK encrypted under the
  current master key) in a new `user_data_key` table: `(id, user_id, key_version, wrapped_dek,
  created_at, destroyed_at)`, unique on `(user_id, key_version)`.
- `User.data_key_ref` (ADR-008/AG-1) is concretely the user's current `key_version` (an integer
  pointer into `user_data_key`), never the key material itself, exactly as AG-1 already specifies
  ("pointer into the keyring, not the key").
- **Master-key rotation** re-wraps the existing `wrapped_dek` rows under the new master key —
  the DEK itself, and therefore every already-encrypted row, is untouched ("rotation re-wraps
  data keys without re-encrypting row data", ADR-004 consequences, unchanged by this ADR).
- **DEK rotation** (a new DEK generation for a user, e.g. suspected key compromise) is an
  operational procedure this ADR documents but does not implement in M6: it requires a background
  re-encryption pass over that user's historical rows and is deferred to whichever milestone first
  needs it.
- **Account erasure / crypto-shred** (ADR-008 item 6): set `destroyed_at` on every
  `user_data_key` row for the user (or hard-delete them). Every row ever encrypted under that
  user's DEK becomes permanently, cryptographically unrecoverable **immediately** — without
  touching a single `memory_event`/`memory`/`decision` row. A later background job hard-deletes
  the now-permanently-opaque ciphertext rows. This means crypto-shred is compatible with
  `memory_event`'s append-only invariant *by construction*: the event rows are never mutated or
  removed by the shred step itself, only the key that made them legible is destroyed.
- **Unresolvable key** (already crypto-shredded user, or KMS unreachable): `db/crypto.py`'s
  decrypt path fails closed — raises a typed error, never returns a placeholder or empty string.
  A crypto-shredded user's data being unreadable is the *correct* terminal state, not a bug to
  route around.

### Where the boundary lives: repository-layer, not a `TypeDecorator`

ADR-004 proposed a SQLAlchemy `TypeDecorator` for this. Rejected here: `TypeDecorator.process_
bind_param`/`process_result_value` receive only the column value and the dialect — no ORM
session, no request context, no `user_id`. Making a *per-user* key available to it would require
a thread-local or `contextvar` carrying the current user across an async boundary — exactly the
kind of implicit global state this codebase has consistently refused elsewhere (`engines/`
receives `now` explicitly rather than reading the wall clock; `events/` takes an `EventStore`
Protocol rather than importing `db/` directly). A `TypeDecorator` would also make the
encrypt/decrypt call invisible at the call site, which cuts against this ADR's own priority order
(explicitness and auditability over convenience).

Instead:

- `db/crypto.py` defines the `KeyProvider` Protocol (`unwrap_user_dek(user_id, key_version) ->
  bytes`) and two pure functions, `encrypt_field(plaintext, *, user_id, table, column, row_id,
  key_provider) -> bytes` and `decrypt_field(envelope, *, user_id, table, column, row_id,
  key_provider) -> str`. The Protocol lives beside its consumer, the same pattern
  `events/store.py` already uses for `EventStore`.
- `db/types.py` defines the envelope struct and its binary pack/unpack — no SQLAlchemy import.
- `security/keyring.py` provides the concrete `KeyProvider` implementations —
  `EnvironmentKeyProvider` (reads the master key from `Settings`, dev/CI default) and
  `FakeKeyProvider` (fixed in-process key material, no env/network, for unit tests). A future
  `KMSKeyProvider` is named here but **not implemented in M6**. `security/keyring.py` implements
  `db.crypto.KeyProvider` *structurally* (Python's `Protocol`) — it never imports `db/`, so `db`
  and `security` stay mutually import-free, matching the sibling-isolation already enforced
  between `engines`/`events`/`llm`.
- `db/models/*.py` declare sensitive columns as plain `LargeBinary` (`BYTEA`) — no custom type.
- `db/repositories/*.py` are the **only** code that calls `encrypt_field`/`decrypt_field`,
  explicitly, when translating between a domain object and an ORM row. This is not a new seam:
  `docs/architecture/01-repository-structure.md` already assigns repositories the job "ORM models
  must not be returned past `services/` — routers see Pydantic DTOs, not ORM rows"; encryption is
  one more translation step at a boundary that already exists.
- The composition root (`services/`, `api/deps.py` — the layer already permitted to import both
  `db` and `security`) is the only place that imports both modules and wires a concrete
  `KeyProvider` into a repository.

Net effect: `domain/`, `events/`, `engines/` never see a key, a nonce, or ciphertext.
`events.types.Event.payload` is always the real decrypted `dict[str, Any]` by the time an `Event`
object exists — decryption happens entirely inside `db/event_store.py`'s adapter, below the
`EventStore` Protocol boundary, so replay, `fold_memory_events`, and `rederive` are unmodified
and encryption-unaware by construction, not by discipline.

## Alternatives considered

1. **Plaintext in M6, encrypt in a later migration.**
2. **SQLAlchemy `TypeDecorator`** with a `contextvar`-carried current user/key.
3. **XChaCha20-Poly1305 via PyNaCl** instead of AES-256-GCM.
4. **Deterministic/searchable encryption** on `email` and other lookup fields, for symmetry.
5. **One shared application-wide key** instead of per-user DEKs.

## Why rejected

1. *Plaintext-then-migrate* directly contradicts ADR-008 ("designed in from milestone 1, not
   bolted on") and this project's own stated principle of not building "looks computed but isn't"
   placeholders. It would also mean a second migration touching every sensitive column, and a
   real risk that "temporary" plaintext reaches a demo, a backup, or a committed fixture before
   the follow-up milestone lands. The user's own instruction for this task — prefer preserving
   the existing privacy invariant over milestone convenience — settles this directly.
2. *`TypeDecorator` + contextvar* works but hides the encryption call, requires get-and-reset
   discipline around every request/session to avoid leaking one user's context into another
   request (a real risk under any async/greenlet reuse), and contradicts "no hidden DB/session
   magic." Explicit repository calls are strictly more auditable for the same result.
3. *PyNaCl/XChaCha20-Poly1305* is a legitimate choice ADR-008 already permits, but it adds a
   second crypto dependency for a nonce-collision margin this system's realistic scale (ADR-001:
   O(10⁴) events per heavy user) never approaches with AES-GCM's 96-bit random nonce. Revisit only
   if per-user event volume assumptions change by orders of magnitude.
4. *Deterministic encryption on `email`* is unnecessary: ADR-008's own enumerated prose-column
   list never names `email`, login requires an equality lookup, and blind-indexing adds real
   complexity (a keyed HMAC column, pepper management) for a field lower in the sensitivity
   ranking than memory/decision content. Plaintext `email` with a normal unique index is the
   smaller, evidence-grounded choice; revisit only if email itself is later classified as needing
   confidentiality beyond normal DB access controls.
5. *One shared key* defeats crypto-shred (ADR-008 item 6): destroying it would erase every user's
   data at once, and a compromise of the single key exposes everyone. Per-user DEKs are the whole
   point of ADR-008's isolation guarantee.

## Consequences

**Positive**
- Crypto-shred stays a single, cheap operation (`destroy user_data_key rows`) regardless of how
  large `memory_event` grows — it never needs to touch the event table.
- `domain/`, `events/`, `engines/` remain provably key-and-cipher-unaware; every existing
  determinism/replay property (ADR-001) is unaffected by construction.
- The encryption boundary is exactly as auditable as SQL itself: `grep` for
  `encrypt_field`/`decrypt_field` finds every place plaintext crosses into ciphertext.

**Negative / costs**
- Repositories carry a small amount of explicit boilerplate per sensitive field (one
  `encrypt_field`/`decrypt_field` call each) instead of it being automatic — an accepted,
  deliberate cost per "Why rejected" #2.
- `db/` and `security/` must stay mutually import-free; enforcing this needs a new
  `.importlinter` contract pair (mirroring `engines-is-pure`) before `db/crypto.py` is written.
- DEK rotation (as opposed to master-key rotation) is specified but not built in M6; a heavy user
  needing it before that milestone exists would have no path yet. Accepted: not a realistic v1
  scenario.

## This ADR does not

Implement any of the above. It is the resolved decision `migrations/0001_*.py` and
`db/crypto.py` must follow once M6 implementation begins.
