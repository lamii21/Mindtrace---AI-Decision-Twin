# MINDTRACE

An **auditable AI decision twin**. It learns how one person weighs trade-offs — from declared
preferences, observed decisions, past experiences, structured elicitation, and outcomes — and
simulates how that person would reason through a new decision.

Core output: **`ACCEPT` / `REJECT` / `UNCERTAIN`** with a *computed* confidence, a credible
interval, per-factor contributions, an evidence chain, and a full decision trace.

## Non-negotiable principle

**The LLM does not make the decision.** It is allowed exactly two jobs:

1. Extract structured information from natural language (schema-validated output).
2. Generate human-readable explanations *from already-computed structured results*.

Everything decision-critical — factor scoring, aggregation, confidence, calibration,
contradiction detection — is deterministic, unit-tested, and reproducible from an event log.

## Status

Phase 0 — architecture & specification. No application code yet. See:

| Document | Purpose |
|---|---|
| [`docs/architecture/01-repository-structure.md`](docs/architecture/01-repository-structure.md) | Directory layout, layering, dependency rules |
| [`docs/architecture/02-domain-model.md`](docs/architecture/02-domain-model.md) | Aggregates, ownership, immutability, projections, lifecycle |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records 001–008 |
| [`schema/factors.yaml`](schema/factors.yaml) | Canonical factor taxonomy (versioned) |
| [`schema/traits.yaml`](schema/traits.yaml) | Canonical trait list + priors (versioned) |
| [`docs/spec/05-mcda-mathematics.md`](docs/spec/05-mcda-mathematics.md) | Formal decision function + hand-worked examples |
| [`docs/spec/06-confidence-model.md`](docs/spec/06-confidence-model.md) | Model-confidence formula (distinct from decision score) |
| [`docs/spec/07-cold-start-interview.md`](docs/spec/07-cold-start-interview.md) | Twin Interview forced-choice scenarios |
| [`docs/api/08-api-contracts.md`](docs/api/08-api-contracts.md) | REST surface + Pydantic schemas |
| [`docs/09-testing-strategy.md`](docs/09-testing-strategy.md) | Test pyramid |
| [`docs/10-security-threat-model.md`](docs/10-security-threat-model.md) | Threat model, guarantees and non-guarantees |
| [`docs/11-roadmap-milestones.md`](docs/11-roadmap-milestones.md) | Small implementation milestones |
| [`docs/PHASE-0-REVIEW.md`](docs/PHASE-0-REVIEW.md) | Brutally honest assessment |

## Stack

Backend: Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · PostgreSQL 16 +
pgvector · numpy · scipy · pytest · arq · structlog · OpenTelemetry.
Frontend: Next.js · TypeScript · Tailwind · Framer Motion · TanStack Query · visx/D3.
Infra: Docker Compose · Redis · GitHub Actions.

No LangChain. No Neo4j. No agent framework. These are deliberate — see ADR-002, ADR-003, ADR-004.
