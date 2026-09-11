# ADR-004 — PostgreSQL + pgvector, no graph database

Status: **accepted** · Date: 2026-09-09

## Context

MINDTRACE stores relational data (users, decisions, predictions), irregular structured data
(options, extracted factors, simulation results), vector embeddings (memory similarity search),
and a provenance graph (`belief → evidence → memory`, occasionally `belief → belief`). The
dossier raised Neo4j as a candidate for the graph and Redis for caching/queues. We need to pick
the smallest datastore set that covers all four without hurting the reproducibility and
deletion guarantees (ADR-001, ADR-008).

## Decision

**One primary datastore: PostgreSQL 16 with the `pgvector` extension.** Plus **Redis**, used
only as the `arq` broker and for ephemeral rate-limit counters — never as a source of truth.

- Relational + JSONB in normal tables. JSONB for `options`, `extracted_factors`, `results`,
  `synthesis`, `trait_snapshot`, `assumptions`; real columns for anything filtered or joined.
- Embeddings in a `vector(1024)` column with an HNSW index, partial `WHERE deleted_at IS NULL`.
  Single-user query space is O(10⁴) rows — pgvector is comfortably sufficient.
- **Provenance graph = the `evidence` table + `WITH RECURSIVE`.** "Why do you believe X" is one
  indexed lookup; the transitive case (belief supported by belief) is a recursive CTE bounded to
  depth ≤ 5. Deletion cascade is a `SELECT belief_id WHERE source_id = ANY(:removed)` feeding the
  re-derivation queue.
- Field-level encryption via a SQLAlchemy `TypeDecorator` (AEAD, per-user key) on prose columns.
- Alembic migrations; a migration is mandatory for any `factors.yaml` / `traits.yaml` schema
  change (ADR-002/005 consequences).

## Alternatives considered

1. **Add Neo4j** for the provenance/knowledge graph.
2. **Add a dedicated vector DB** (Qdrant / Weaviate / Pinecone) alongside Postgres.
3. **SQLite** for v1 simplicity.
4. **Redis as a read-through cache** for projections.
5. **A separate OLAP store** (DuckDB/ClickHouse) for the evaluation metrics.

## Why rejected

1. **Neo4j.** The graph here is shallow (depth 2–3, occasionally 5), single-tenant, and small
   (hundreds of edges per user). A recursive CTE answers every query we have. Adding Neo4j means
   a second datastore to run, back up, migrate, secure, and — critically — **keep consistent
   with Postgres**, which reintroduces exactly the dual-write / reconciliation problem that
   ADR-001 works to avoid. It would be resume-driven design (principle 12). Revisit only if
   profiling shows recursive-CTE provenance queries dominating latency at realistic data
   volumes — which is not credible at this scale.
2. **Dedicated vector DB.** Same "second datastore, dual writes, separate deletion path"
   objection. Deletion guarantees (ADR-008) are far easier when the vector lives in the same row
   as the ciphertext and disappears in the same `DELETE`. pgvector's recall/latency are a
   non-issue for per-user corpora.
3. **SQLite.** No `pgvector`, weak concurrent-writer story for the worker, no RLS, and we would
   migrate away almost immediately. Not worth the throwaway.
4. **Redis cache for projections.** Projections are already cheap to read from Postgres and must
   be *authoritative* and rebuildable; caching them adds an invalidation problem and a second
   place a stale belief can hide. Redis stays out of the correctness path.
5. **Separate OLAP store.** Evaluation runs over hundreds–thousands of prediction/outcome rows
   per user. Plain SQL aggregates + numpy in the worker are ample. Adding ClickHouse would be
   infrastructure with no user at this scale.

## Consequences

**Positive**
- One backup, one restore drill, one migration history, one place deletion has to work.
- Transactional consistency between a belief, its `evidence` edges, and its `audit_log` row —
  they commit together.
- `testcontainers[postgres]` gives integration tests a real engine incl. `pgvector` and RLS.
- The whole store is explainable on a whiteboard in the interview.

**Negative / costs**
- `pgvector` HNSW index build/rebuild is not free; fine at our scale, noted for later.
- Heavy JSONB fields (`results`, `trait_snapshot`) are opaque to SQL filtering. Accepted: nothing
  queries inside them; they are read whole by the service layer. Anything that later needs
  filtering gets promoted to a column + a migration.
- Recursive CTEs need care (cycle guard, depth cap). Encapsulated in one repository method with
  its own tests.
- Postgres becomes a single point of failure. For a portfolio deployment this is acceptable;
  the runbook covers managed-Postgres backups + a restore test (milestone in the roadmap).
