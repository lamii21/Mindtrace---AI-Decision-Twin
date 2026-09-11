# Architecture Decision Records

Format: Context · Decision · Alternatives considered · Why rejected · Consequences.
An ADR is immutable once `accepted`; a reversal is a new ADR that supersedes it.

| ADR | Title | Status |
|---|---|---|
| [001](ADR-001-event-sourced-memory.md) | Event-sourced memory | accepted |
| [002](ADR-002-deterministic-mcda-decision-engine.md) | Deterministic MCDA decision engine | accepted |
| [003](ADR-003-llm-boundary.md) | LLM boundary | accepted |
| [004](ADR-004-postgresql-pgvector.md) | PostgreSQL + pgvector, no graph DB | accepted |
| [005](ADR-005-bayesian-preference-estimation.md) | Bayesian preference estimation | accepted |
| [006](ADR-006-computed-confidence.md) | Computed model confidence | accepted |
| [007](ADR-007-parallel-twin-architecture.md) | Parallel twin architecture | accepted |
| [008](ADR-008-privacy-and-provenance.md) | Privacy and provenance | accepted |

Cross-cutting invariant all eight serve: **beliefs are a pure function of `(event log,
engine_version, factor_schema_version, seed)`** and the LLM never contributes a number used in a
calculation.
