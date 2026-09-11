# ADR-006 — Computed model confidence

Status: **accepted** · Date: 2026-09-09 · Related: ADR-002, ADR-005, ADR-007

## Context

"Confidence: 76%" is the single most abused number in AI products. In MINDTRACE it must mean
something specific and be defensible line-by-line. It must never come from an LLM (principle 2),
must never be conflated with the decision score `S` (ADR-002), and must be *calibrated* against
reality once data exists.

Two distinct quantities are routinely confused and must be kept separate everywhere in code, API,
and UI:

| Quantity | Symbol | Meaning | Range | Source |
|---|---|---|---|---|
| **Decision score** | `S` | How strongly the twin's preferences favour the option | [−1, 1] | `engines/mcda` weighted-additive value |
| **Model confidence** | `C` | How much the system trusts its *own* answer for this decision | [0, 1] | `engines/confidence`, this ADR |

A high `S` with low `C` is a normal, displayable state ("preferences point to ACCEPT, but I don't
have enough evidence to stand behind it").

## Decision

`C` is a **deterministic function of five computed inputs**, none LLM-derived:

```
C = g( a · evidence_sufficiency
     + b · (1 − ensemble_disagreement)
     + c · historical_calibration
     + d · (1 − extraction_entropy)
     + e · margin_adequacy )
```

with `g` a squashing/clamping map to [0,1] and `a+b+c+d+e = 1`.

Inputs (full formulas in [`docs/spec/06`](../spec/06-confidence-model.md)):

1. **`evidence_sufficiency`** — from the Bayesian posteriors (ADR-005): a function of the
   *effective sample size* behind the traits that carry weight in *this* decision, and of
   coverage (share of decision weight on `known` factors). Saturating (`1 − e^{−N_eff/k}`).
2. **`ensemble_disagreement`** — dispersion of the decision across the parallel twins (ADR-007):
   normalised spread of their scores `S`, plus an indicator if they don't all agree on the
   `ACCEPT/REJECT/UNCERTAIN` label. This is where "the four of you disagree" pulls `C` down.
3. **`historical_calibration`** — `1 − ECE` (expected calibration error) over the user's past
   predictions **in the same decision domain**, with a Bayesian shrink toward a pessimistic
   prior while the sample is small. Below a sample-size gate it contributes a fixed low value,
   not a guess.
4. **`extraction_entropy`** — uncertainty in the LLM factor extraction: from the count of
   factors returned `known=false`, and (if available) the model's own token-level uncertainty /
   a self-consistency check across 2 extraction samples. Used only to *reduce* `C`, never to set
   a decision.
5. **`margin_adequacy`** — how far `S` sits from the nearest threshold, normalised by a
   reference margin. A knife-edge decision is low-confidence even with lots of evidence.

**Weights `a…e` are themselves fixed constants in v1** (`a=0.35, b=0.20, c=0.20, d=0.10,
e=0.15`), chosen by reasoning documented in spec §06, **not** fitted — there's no data to fit
them to at launch. Once the prediction ledger has ≥ N labelled points, a logistic recalibration
(`P(correct) ~ σ(α + β·raw_C)`) is fitted offline in `notebooks/confidence_calibration.ipynb`,
reviewed, version-bumped, and applied — and that recalibration is logged like any engine change.
Until then the Report Card explicitly shows "confidence not yet calibrated (n/N)".

Hard gate (from ADR-002, restated): `margin < MARGIN_MIN` **or** `coverage < COVERAGE_MIN`
**or** `C < C_MIN` ⇒ the decision label is `UNCERTAIN` regardless of `S`.

## Alternatives considered

1. **LLM emits a confidence field.** Rejected by principle 2, non-negotiable.
2. **`C = |S|`** (use the decision score's magnitude as confidence).
3. **Posterior-only**: `C` = a function of trait CIs alone.
4. **Conformal prediction** over the decision output.
5. **Skip `C` entirely**; only ever show `ACCEPT/REJECT/UNCERTAIN`.

## Why rejected

1. Fabricated, uncalibrated, irreproducible.
2. Conflates the two quantities this ADR exists to separate. A confident-looking `S` can come
   from one strongly-weighted but poorly-evidenced factor. Misleading.
3. Ignores ensemble disagreement, extraction quality, margin, and — crucially — the *track
   record*. A twin can have tight CIs and still be systematically wrong; only `historical_
   calibration` catches that.
4. Conformal prediction is principled and appealing but needs a sizeable calibration set per
   user to give non-trivial intervals; with 15–40 decisions the sets are useless. Kept as a v2
   research direction once multi-user calibration is on the table.
5. Losing `C` throws away the product's headline honesty feature and the mechanism that makes
   `UNCERTAIN` fire for the right reasons. The dossier's whole pitch is calibrated uncertainty.

## Consequences

**Positive**
- Every term is separately unit-testable (`test_evidence_sufficiency_saturates`,
  `test_disagreement_pulls_confidence_down`, …) and independently inspectable in the UI's "how
  was this confidence computed" panel.
- `C` and `S` have different names, types, and columns end-to-end; a lint/test guards against
  a response DTO that exposes one as the other.
- Report Card can plot raw vs calibrated `C` once data exists — a strong interview artefact.

**Negative / costs**
- Five hand-set weights and several constants (`k`, `MARGIN_MIN`, `COVERAGE_MIN`, `C_MIN`,
  sample gates). All in one config module, all documented with rationale, none secret. Honest
  framing: "these are engineering priors, scheduled for empirical recalibration".
- `historical_calibration` is near-useless for the first ~20 decisions; during that window `C`
  is dominated by evidence/disagreement/margin and the UI says so.
- Self-consistency extraction sampling doubles that LLM call's cost; gated to when the first
  extraction has many `unknown`s.
