# 07 — Cold-start Strategy: the Twin Interview

Status: **accepted (Phase 0)** · Canonical data: [`schema/interview.yaml`](../../schema/interview.yaml) v1 · Implements the prior for ADR-005

---

## 1. The problem it solves

A new twin has only wide priors (spec §04). Asking "what are your values?" yields socially-
desirable noise. The Twin Interview instead observes **choices** between concrete synthetic
options and infers the value function that best explains them — the *same* linear-additive value
function the MCDA engine uses (spec §05), so there is no train/serve mismatch.

Target: **18–24 items, ~8–12 minutes.** This will *not* fully identify 16 weights + 4
dispositions — posteriors stay wide, and many of the twin's first decisions will be
`UNCERTAIN`. That is the correct, honest outcome (principle 16), not a bug to paper over.

---

## 2. Structure

1. **Likert warm-up (≤ 5 items).** 1–5 importance ratings for the five high-`self_report_
   reliability` factors. Effect: nudges prior `μ_i` by at most `0.3·(rating−3)/2` for those
   factors only. Declarations *tilt* the prior; they never anchor it.
2. **Fixed prefix (12 pairwise items, `p01`–`p14` minus the two `…r` repeats).** Chosen so every
   core factor appears in `covers:` at least once. Deterministic order.
3. **Adaptive suffix (≤ 12 items).** After the prefix, pick the next item to **maximise expected
   information gain** about the current posterior (see §5). Includes disposition items
   (`d01`–`d08`) and the two consistency-check repeats (`p03r`, `p07r`). Stop when
   `18 ≤ answered ≤ 24` **and** the best remaining item's expected gain `< ε`.
   *v1 milestone note:* the first shippable version may use a **fixed** suffix (a preset order
   of `d01,d03,d05,d07,p03r,p07r,d02,d04,…`); the adaptive selector is a fast-follow. The
   contract and the update math are identical either way.

Answers: `A`, `B`, or `indifferent`. Response latency is recorded (not yet used in v1; reserved
for a future noise model).

---

## 3. Modelling assumptions — stated explicitly

1. **Random-utility choice model** (Thurstone Case V / Bradley–Terry): the probability of
   choosing A over B is logistic in the weighted difference of their factor profiles, with
   i.i.d. noise. Users are **not** assumed to be perfect maximisers — the logistic scale `s`
   absorbs stochasticity.
2. **Linear-additive utility** over the anchored, polarity-corrected factor scale — identical to
   the MCDA aggregator.
3. **Synthetic option profiles are on the same scale** as LLM factor extraction (`vl…vh` →
   `factors.yaml` anchors), so interview evidence and decision evidence are directly comparable.
4. **Marginal independence across trait dimensions** (diagonal covariance) — v1 simplification
   (spec §04 §7).
5. **Stationarity for the interview's duration** (~10 min).
6. **The interview under-determines absolute scale.** Only *relative* weights are recovered;
   the mean-zero gauge (spec §04 §2) fixes it.
7. **Answers are noisy and possibly inconsistent.** Consistency-check items (`p03r`, `p07r` —
   earlier items with options swapped) estimate a per-user `interview_noise ∈ [0,1]`; a
   disagreement inflates the effective `s` for that user and **caps the initial trait
   confidence** (so an inconsistent respondent gets a suitably humble twin).

---

## 4. How an answer updates the posterior

### 4.1 Pairwise items → weight logits `θ`

Each pairwise item `k` has a precomputed **design vector** `x_k` with
`x_{k,i} = n_i(A_k) − n_i(B_k)` over the factors it varies (0 elsewhere), where `n` is the
normalised polarity-corrected level (spec §05 §1; the *neutral-disposition* curve, `γ = 1`, is
used for interview scoring so the prior does not depend on dispositions that are themselves being
estimated).

Likelihood of the observed choice `y_k ∈ {1 = chose A, 0 = chose B}`:

```
P(y_k = 1 | θ) = σ( (1/s_user) · θ·x_k )        s_user = s · (1 + interview_noise)
```

`indifferent` is modelled as a soft observation: a fractional count `y_k = 0.5` with half weight.

**Update.** Rather than update incrementally per item (Laplace error accumulates), the interview
accumulates all `(x_k, y_k, weight_k)` and, at the end, runs **one** Laplace pass (spec §04 §3):
25 damped Newton steps on `Σ_k weight_k · logistic_loglik(y_k | θ·x_k / s_user) + logPrior(θ)`,
then `μ ← θ_MAP`, `Σ⁻¹ ← Σ_prior⁻¹ + Xᵀ diag(p(1−p)/s_user²) X` (diagonal kept), re-impose
mean-zero gauge. Seeded, fixed iterations → reproducible.

### 4.2 Disposition items → Beta posteriors

Each disposition item targets exactly one disposition `p` and yields `y ∈ {0,1}`:

| item type | `y = 1` when the user chose… | maps to |
|---|---|---|
| `gamble` | the risky option | `risk_tolerance` ↑ |
| `intertemporal` | the delayed-larger option | patience ↑ ⇒ **`time_discount` ↓** (update uses `1 − y`) |
| `ambiguity` | the unknown-probability option | ambiguity-tolerance ↑ ⇒ **`ambiguity_aversion` ↓** (uses `1 − y`) |
| `effort` | the high-intensity option | `effort_tolerance` ↑ |

Conjugate pseudo-count update: `α ← α + κ·y_eff`, `β ← β + κ·(1 − y_eff)`, `κ = 1.5`,
`y_eff` = `y` or `1 − y` per the table. `indifferent` → `α ← α + κ/2`, `β ← β + κ/2`.

### 4.3 Finalisation

After the last item: run the consolidated Laplace pass (§4.1), compute `interview_noise` from
consistency checks, apply the confidence cap, then:

- create `Twin` + first `TwinVersion` (`reason = post_elicitation`, `engine_version`,
  `factor_schema_version`, `trait_schema_version`);
- write `Evidence` edges: one per pairwise item per varied factor (`source_kind =
  elicitation_answer`, `weight = |x_{k,i}|·weight_k`, `polarity` by sign), one per disposition
  item;
- traits report `source = "declared"` until `min_evidence_for_inferred` decision-derived edges
  also exist;
- emit `elicitation_answered` events (one per item) so the whole interview is replayable
  (ADR-001) and a re-derivation reproduces the identical first `TwinVersion`.

---

## 5. Adaptive item selection (expected information gain)

For candidate item `c` with design vector `x_c` and current posterior `N(μ, Σ)`:

```
p_c      = σ( μ·x_c / s_user )                       # predicted choice prob
var_pred = x_cᵀ Σ x_c                                # predictive variance along x_c
EIG(c)  ≈ p_c(1−p_c) · var_pred / ( s_user² + p_c(1−p_c)·var_pred )
```

(the expected reduction in posterior entropy from a Bernoulli-logistic observation, Laplace
approximation). Pick `argmax_c EIG(c)` among unseen items, with two constraints: don't pick a
consistency-check repeat before its original, and cap how many disposition items of one `target`
are asked (≤ 3). Disposition items use the analogous Beta entropy-reduction expression.

Deterministic given the posterior ⇒ the whole interview trajectory is reproducible from the
answer log.

---

## 6. Item bank (v1, `schema/interview.yaml`)

| id | type | targets / factors varied |
|---|---|---|
| p01 | pairwise | financial_return · time_demand · health_wellbeing |
| p02 | pairwise | skill_growth · financial_return |
| p03 / p03r | pairwise (+ consistency) | stability · location_fit · financial_security · intrinsic_interest |
| p04 | pairwise | autonomy · social_fit |
| p05 | pairwise | creative_expression · downside_risk · reversibility |
| p06 | pairwise | values_alignment · financial_return |
| p07 / p07r | pairwise (+ consistency) | option_value · intrinsic_interest |
| p08 | pairwise | reversibility · financial_return |
| p09 | pairwise | long_term_value · time_demand · financial_return |
| p10 | pairwise | financial_return · financial_security |
| p11 | pairwise | skill_growth · health_wellbeing · time_demand |
| p12 | pairwise | location_fit · skill_growth · option_value |
| p13 | pairwise | autonomy · creative_expression · social_fit |
| p14 | pairwise | stability · financial_security · skill_growth |
| d01, d02 | gamble | risk_tolerance |
| d03, d04 | intertemporal | time_discount |
| d05, d06 | ambiguity | ambiguity_aversion |
| d07, d08 | effort | effort_tolerance |

24 items total; every core factor covered ≥ once by the fixed prefix; each disposition has 2
dedicated items plus indirect signal from the pairwise set.

---

## 7. Tests (`tests/unit/elicitation/`, `tests/property/`)

- **Recovery:** simulate a synthetic user with known `θ*`; feed noiseless answers to the full
  bank; assert `μ` lands within CI of `θ*` on the covered directions and CIs shrink vs prior.
- **Monotonic evidence:** answering `p02` "A" (learning over pay) never decreases `μ_skill_growth`
  and never increases `μ_financial_return`.
- **Consistency check:** contradictory `p03` vs `p03r` raises `interview_noise` and lowers all
  trait `confidence` outputs.
- **Reproducibility:** same answer log ⇒ byte-identical first `TwinVersion`; replay of the
  `elicitation_answered` events reproduces it.
- **Beta updates:** `d01`–`d08` produce the exact closed-form `Beta` posteriors.
- **Adaptive selector determinism:** given a posterior, `argmax EIG` is stable and never selects
  a repeat before its original.
- **Under-identification is honest:** after only the 12-item prefix, at least half the traits
  still report `confidence < low_confidence_threshold`, and a mid-difficulty decision returns
  `UNCERTAIN`.
