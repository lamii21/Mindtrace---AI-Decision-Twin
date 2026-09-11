# ADR-002 — Deterministic MCDA decision engine

Status: **accepted** · Date: 2026-09-09

## Context

The product's central claim is that MINDTRACE *reasons*, auditably, rather than *guessing*
plausibly. The decision output (`ACCEPT`/`REJECT`/`UNCERTAIN` + confidence + per-factor
contributions + trace) must be:

- reproducible bit-for-bit given the same inputs,
- explainable as arithmetic a human can follow,
- unit-testable with hand-worked examples,
- immune to the failure mode where the explanation and the decision disagree (which happens when
  an LLM produces the decision and a separate call rationalises it).

We also need per-factor *contribution* numbers (the "Career growth +31%" in the dossier) to fall
out of the computation, not be narrated.

## Decision

The decision is produced by a **Multi-Criteria Decision Analysis** core in `engines/mcda/`,
formally specified in [`docs/spec/05-mcda-mathematics.md`](../spec/05-mcda-mathematics.md):

1. **Factor extraction** (LLM, schema-validated) maps the situation to a level per factor per
   option, plus a per-factor `known` flag.
2. **Normalisation** maps each factor level to a common polarity-corrected scale using the
   direction metadata in `factors.yaml`.
3. **Weighting** uses the twin's `WeightVector` (derived from trait posteriors, ADR-005),
   renormalised over the *known* factors only.
4. **Aggregation** is a weighted additive value function; total score `S ∈ [−1, 1]`.
5. **Contribution** of factor *i* is `w_i · n_i` reported as a signed share of `Σ|w_i · n_i|`.
6. **Decision rule**: `S ≥ τ_accept → ACCEPT`; `S ≤ τ_reject → REJECT`; else `UNCERTAIN`.
   Additionally `margin = |S − τ_mid|` and coverage (share of weight on known factors) gate to
   `UNCERTAIN` below thresholds.

Weighted-additive is the v1 aggregator. TOPSIS is kept as an alternative implementation behind
the same interface for a later comparison study (not shipped in v1).

Every function in `engines/mcda/` is pure: `(inputs, config, engine_version) → result`. No I/O,
no clock, no RNG.

## Alternatives considered

1. **LLM produces the decision + confidence directly** (structured output: `{decision,
   confidence, reasons}`).
2. **LLM produces the decision; a rules layer only vetoes.**
3. **Learned model** (gradient-boosted trees / small MLP) trained on the user's decisions.
4. **Full utility-theory / AHP with pairwise comparison matrices.**
5. **Outranking methods (ELECTRE/PROMETHEE)** instead of weighted-additive.

## Why rejected

1. This *is* the "GPT wrapper" the project exists to avoid (principles 1–3). Not reproducible,
   not testable, confidence is fabricated (principle 2), and the explanation is a post-hoc story.
2. Still lets the LLM set the answer in the common case; the veto layer is untestable against
   the space of things the LLM might say. Explanation/decision can still diverge.
3. **Data.** A portfolio user supplies 15–40 decisions total. That will not fit a supervised
   model with useful generalisation; it will memorise and mislead. Revisit only if a user ever
   accumulates hundreds of labelled decisions (it won't in the target scenario).
4. AHP's pairwise matrices are elegant but impose O(n²) elicitation on the user for n factors
   and add consistency-ratio machinery. The forced-choice interview (spec §07) gets us weights
   more cheaply. AHP kept as background reading, not a dependency.
5. Outranking methods handle incomparability well but their thresholds (preference/indifference/
   veto per criterion) are *more* free parameters to justify, and their output is a partial
   order that is harder to render as a single `ACCEPT/REJECT` + contribution bars. Weighted-
   additive is the honest minimum; complexity must earn its place (principle 9).

## Consequences

**Positive**
- `tests/golden/data/mcda_examples/*.json` — the 5 hand-worked examples from spec §05 become
  golden tests on day one. A change to the math is a visible diff requiring review.
- Property tests: monotonicity (raising a positively-directed known factor never lowers `S`),
  bounds (`S ∈ [−1,1]`, contributions sum to ±100%), tie → `UNCERTAIN`, permutation invariance
  of factor order.
- Contribution numbers are defined, not narrated. The trace graph in the UI renders real values.
- The engine runs in a notebook with no infra — good for the calibration studies and the
  interview demo.

**Negative / costs**
- Weighted-additive assumes preferential independence of factors. Real trade-offs sometimes
  interact (salary matters *less* once above a threshold). v1 mitigation: non-linear per-factor
  normalisation curves (diminishing returns) declared in `factors.yaml`; documented limitation
  otherwise. Interaction terms are a deliberate v2 question (PHASE-0-REVIEW).
- Thresholds `τ_accept`, `τ_reject`, coverage/margin minima are free parameters. They are
  **fixed constants in v1**, documented, and only later tuned against the prediction ledger — and
  that tuning is itself logged and versioned.
- Garbage-in risk: if factor extraction is wrong, the math faithfully computes a wrong answer.
  Mitigation: the `known` flag + coverage gate + user-editable extracted factors in the trace UI.
