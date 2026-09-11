# 03 — Factor Model

Status: **accepted (Phase 0)** · Canonical data: [`schema/factors.yaml`](../../schema/factors.yaml) v1 · Related: ADR-002

---

## 1. What a "factor" is

A factor is one **dimension of value** along which any decision option can be placed. The MCDA
engine (spec §05) scores an option as a weighted combination of its per-factor levels. Factors
are:

- **domain-general** — the same 16 work for a job offer, a degree programme, a laptop purchase,
  a house move, a relationship decision;
- **preferentially near-independent** — chosen so a person can trade one against another without
  a third silently changing (weighted-additive requires this; see ADR-002 limitation);
- **observable in prose** — the LLM extractor can place an option on a 5-level ordinal scale
  from a natural-language description.

There are exactly **16 core factors** plus **3 extended factors** defined but near-zero-weighted
in v1.

---

## 2. Critical evaluation of the dossier's starter list

The dossier proposed: `financial_security, growth, learning, autonomy, stability, location,
social_environment, creativity, time_cost, risk, long_term_value, impact, convenience`.
Changes made and why:

| Dossier term | Verdict | Change |
|---|---|---|
| `growth` + `learning` | **Collapsed & split differently.** "Growth" was doing three jobs (skills, career doors, compounding). | → `skill_growth` (transferable capability), `option_value` (future choice set), `long_term_value` (compounding). Cleaner trades; needed distinctly for "Future You". |
| `financial_security` | **Split.** Conflated *amount* and *variance*. | → `financial_return` (net money, signed) + `financial_security` (predictability/safety margin). |
| `risk` | **Sharpened & split.** Ambiguous between "variance", "chance of disaster", "irreversibility". | → `downside_risk` (severity×likelihood of a bad outcome, cost) + `reversibility` (can it be undone, benefit). Income variance already lives in `financial_security`. |
| `location` | Kept, renamed | → `location_fit` (proximity, relocation burden, commute, environment). |
| `social_environment` | Kept, renamed | → `social_fit` (people & culture quality, mentorship, safety). |
| `creativity` | Kept, renamed | → `creative_expression` (room to originate vs execute a spec). |
| `time_cost` | Kept, renamed, absorbed `convenience` | → `time_demand` (hours + cognitive load + logistical hassle). |
| `convenience` | **Removed as standalone.** ~80% overlap with `time_demand`; a separate low-signal factor dilutes weight estimation. | Folded into `time_demand`. |
| `impact` | **Split & partly demoted.** Mixed "meaning to me" with "benefit to others". | → `values_alignment` (core: principled/identity fit, incl. named causes) + `external_impact` (extended: separately-traded altruism). |
| `autonomy`, `stability`, `long_term_value` | Kept as-is | — |
| — | **Added** `intrinsic_interest` (day-to-day enjoyment — highly decisive, was missing), `health_wellbeing` (stress/hours/rest — routinely decisive, was missing). | new core factors |
| — | **Added extended** `social_standing` (prestige — under-reported but real), `novelty` (change for its own sake). | defined, ~0 weight in v1 |

Design guard against genericness: every factor entry in the YAML carries `examples` and
`possible_evidence` for **at least two different decision domains**, and a factor that could not
be given concrete cross-domain evidence was cut.

---

## 3. Scale semantics

Each option gets, per factor, one of `{very_low, low, moderate, high, very_high}` **and** a
`known: bool` from the extractor. `known: false` (the model genuinely cannot tell from the input):

- the factor is dropped from that option's aggregation,
- weight is renormalised over the remaining known factors,
- **coverage** = Σ(weight on known factors) drops, feeding the `UNCERTAIN` gate (spec §05) and
  `evidence_sufficiency` (spec §06).

Levels map to `[0,1]` **anchors** (linear by default; `financial_return`, `downside_risk`
override with non-linear anchors reflecting diminishing returns / accelerating pain). Then
**polarity correction**: `direction: benefit` → `n = anchor`; `direction: cost` → `n = 1 −
anchor`. So after normalisation, **higher `n` is always better**, uniformly, for the aggregator.

Two `direction: cost` factors: `time_demand`, `downside_risk`. Everything else is `benefit`.

Per-user curve shaping: `downside_risk`, `financial_security`, `time_demand`, `reversibility`
normalisation curves are **bent by dispositions** (`risk_tolerance`, `effort_tolerance`,
`ambiguity_aversion` — see [`04-trait-model.md`](04-trait-model.md) §4). This is the one place a
trait touches the *normalisation* step rather than the *weights*, and it is fully deterministic.

---

## 4. Extraction contract (LLM boundary)

`llm.extract` returns, per option, a `FactorExtraction` Pydantic model:

```
FactorExtraction:
  option_id: str
  factors: dict[FactorId, FactorReading]     # keys must be exactly the 16 core ids
FactorReading:
  level: Literal["very_low","low","moderate","high","very_high"]
  known: bool
  rationale_span: str        # the substring of the input the level was read from (≤ 240 chars)
```

Constraints enforced by the schema (`extra="forbid"`, enum levels, all 16 keys required):
if any key is missing or extra, or an enum is violated → `ExtractionValidationError` →
deterministic fallback: **all factors `known=false`** → coverage 0 → `UNCERTAIN`. The extractor
**cannot** return a number, a weight, or a confidence (ADR-003 rule 1). `rationale_span` is
stored and shown in the trace so the user can see *what text* drove each level and correct it.

---

## 5. Versioning & migration

`schema/factors.yaml` has a `version`. `factor_schema_version` is stamped on every `TwinVersion`,
`Prediction`, `Simulation`. Rules:

- **Additive change** (new extended factor, new example, doc text): minor; no migration, but a
  `CHANGELOG.md` entry.
- **Structural change** (add/remove core factor, change `direction`, change `anchors`, move a
  factor between core/extended): **major**; requires an Alembic migration that (a) records the
  new version, (b) enqueues a full twin re-derivation for every user, (c) marks pre-migration
  `Prediction`s as `schema_version_stale` so the Evaluation Engine can segment them.
- Cross-version comparison in the UI (Evolution timeline, Counterfactual Replay) is only offered
  between snapshots sharing a `factor_schema_version`; otherwise the UI shows a "schema changed
  here" marker.

---

## 6. Open questions (tracked in PHASE-0-REVIEW)

- Is 16 the right number? Risk of sparsity: with ≤ 40 decisions, estimating 16 weights is
  already ambitious. A **v1 experiment**: run the interview-only prior against a reduced 8-factor
  set and compare consistency scores.
- Preferential independence is violated by `financial_return`×`financial_security` and
  `time_demand`×`health_wellbeing`. v1 relies on curve shaping + documentation; interaction
  terms are a v2 candidate.
- `downside_risk` and `reversibility` self-report reliability is `low` — these may be better
  left inference-only even in the interview.
