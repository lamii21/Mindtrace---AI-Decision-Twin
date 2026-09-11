# 04 — Trait Model

Status: **accepted (Phase 0)** · Canonical data: [`schema/traits.yaml`](../../schema/traits.yaml) v1 · Related: ADR-005, ADR-006

---

## 1. Honest scope

MINDTRACE does **not** infer personality. It infers the parameters of a *decision value
function*: how much this person weights each factor, plus four dispositions that shape how those
weights are applied. That is all a "trait" is here. With 20–30 interview answers and 15–40
observed decisions we cannot, and do not claim to, recover stable psychological constructs. The
model's job is to represent **what it does and does not know**, and to let that uncertainty
propagate to `UNCERTAIN`.

---

## 2. The trait vector

| Group | Members | Posterior | Count |
|---|---|---|---|
| **Importance weights** | one per core factor (`w_financial_return`, … `w_reversibility`) + 3 extended pinned near 0 | `θ_i ~ Normal(μ_i, σ_i²)` on a logit scale; `w = softmax(θ)` at read | 16 (+3) |
| **Dispositions** | `risk_tolerance`, `time_discount`, `ambiguity_aversion`, `effort_tolerance` | `p ~ Beta(α, β)` on [0,1] | 4 |

### Observable / inferred / latent

- **Directly observable:** *none*. Even interview answers are treated as noisy *observations of*
  latent parameters via a choice model, not as declarations of the parameters themselves.
- **Inferred (has an update path from data):** all 16 weights, all 4 dispositions.
- **Latent (never directly measured, only estimated):** the dispositions especially — they are
  constructs, reported with wide intervals early and flagged `source: declared` until
  `min_evidence_for_inferred` (2) edges exist.

### Gauge fix (identifiability)

`softmax` is invariant to adding a constant to all `θ_i`, so individual `μ_i` are not
identifiable in isolation. We constrain `Σ μ_i = 0` after every update (subtract the mean). All
reporting and all engine use is of **relative** weights. Spec §05 aggregation only ever uses
`softmax(θ)` over the known set, which is well-defined.

---

## 3. Priors, likelihood, posterior — precisely

### Prior

From `traits.yaml`: weights `μ ≈ 0` (a few small non-zero nudges for factors people reliably
rate highly, e.g. `skill_growth`), `σ = 1.4–1.5` (wide — a factor's weight could plausibly be
2–3× another's). Dispositions `Beta(2,2)` or a mild skew. A user's **self-rated importances**
from the interview's Likert warm-up shift the prior `μ` by at most `0.3·(rating−3)/2` and only
for factors with `self_report_reliability: high` — declarations nudge, they do not anchor.

### Likelihood — two observation types

**Forced-choice interview answer** "A ≻ B":

```
P(A ≻ B | θ) = σ(  (1/s) · Σ_i θ_i · ( n_i^A − n_i^B )  )
```

where `n_i^X` is the polarity-corrected normalised level of factor *i* in option *X* (spec §03),
`s` is a fixed logistic scale (`traits.yaml`, v1 `s = 0.6`), `σ` the logistic function. This is
a Bradley–Terry / Thurstone-case-V model with the twin's weights as the latent utility
coefficients.

**Observed decision** "chose option *k* from {options}": modelled as *k* maximising the value
function, approximated by the pairwise product `Π_{j≠k} P(k ≻ j | θ)` (a Plackett-Luce-style
factorisation), each pair using the same link.

### Posterior update — deterministic Laplace step

No conjugacy (logistic link). Per update:

1. Start from current `Normal(μ, Σ)` (Σ diagonal in v1).
2. Compute the MAP by **N Newton steps** (fixed `N = 25`, fixed damping) on
   `log P(obs | θ) + log Prior(θ)`.
3. Set new `μ = θ_MAP`; new `Σ⁻¹ = Prior_precision + (−∇² log P(obs | θ_MAP))` (observed Fisher
   information); keep only the diagonal.
4. Re-impose the mean-zero gauge.

Dispositions: where an interview item targets a disposition directly (e.g. a pure risk gamble),
update its `Beta` with a **pseudo-count** rule (`α += κ·answer`, `β += κ·(1−answer)`, `κ = 1.5`),
which *is* conjugate and trivially testable. Decisions update dispositions only indirectly, via
their mechanical link to the weights (a person repeatedly accepting high `downside_risk` options
raises `w`-consistency that the disposition estimator reads).

Everything is seeded, fixed-iteration, tolerance-bounded → **bit-reproducible** across runs and
platforms. `engines/preference/update.py` is unit-tested against:
- a pure-Gaussian likelihood (Laplace step must equal the exact conjugate posterior),
- a single `Beta` update (must equal the closed form),
- a monotonicity property (an answer favouring factor *i* never decreases `μ_i`).

---

## 4. How dispositions modulate the MCDA (deterministic links)

| Disposition | Link | Formula (v1) — exact curve convention in [`05-mcda-mathematics.md`](05-mcda-mathematics.md) §2 |
|---|---|---|
| `risk_tolerance` | exponent of the `downside_risk` (cost) and `financial_security` (benefit) normalisation curves | `γ = k_risk^(2·risk_tolerance − 1)`, `k_risk = 1.7`. Applied as `shaped = a^γ` on the raw anchor `a` **before** polarity correction. `risk_tolerance = 0.5 ⇒ γ = 1` (linear). |
| `effort_tolerance` | exponent of the `time_demand` cost curve | `γ = k_effort^(2·effort_tolerance − 1)`, `k_effort = 1.6`. Same application. |
| `time_discount` | multiplier on the *adjusted weight* of `option_value` & `long_term_value` before the known-set renormalisation; "Future You" shift size | `m = 1 − 0.6·time_discount`; `w_adj_i *= m` for those two factors; `shift_future ∝ time_discount` |
| `ambiguity_aversion` | multiplier on the *adjusted weight* of `reversibility`; per-user `COVERAGE_MIN` | `w_adj_reversibility *= (1 + 0.4·ambiguity_aversion)`; `COVERAGE_MIN_user = COVERAGE_MIN + 0.15·ambiguity_aversion` |

Note: `risk_tolerance`/`effort_tolerance` bend the **normalisation** of specific factors;
`time_discount`/`ambiguity_aversion` scale specific **adjusted weights**. Neither ever touches
the aggregation formula itself.

Each link has its own unit test asserting the extreme-value behaviour and monotonicity. The
links are **fixed design**, documented as "pending empirical study" (PHASE-0-REVIEW), not
learned.

---

## 5. Reporting (API / UI contract)

Per trait:

```
TraitReport:
  id: str                    # factor id or disposition id
  value: float               # posterior mean on the reporting scale (weights: share in [0,1]; dispositions: [0,1])
  confidence: float          # in [0,1] - see below
  credible_interval: {low: float, high: float}   # 90% marginal
  evidence_count: int        # Evidence edges supporting this trait
  source: "declared" | "inferred"
  trend: "rising" | "falling" | "stable" | null  # from Evolution Engine, null until 2+ snapshots
```

`confidence` is **not** ADR-006 model confidence (that is per *decision*). It is a per-trait
learning indicator:

```
confidence = clip( sqrt( 1 − σ_post / σ_prior ), 0, 1 )    # weights
confidence = clip( 1 − sd(Beta(α,β)) / sd(Beta(2,2)), 0, 1 ) # dispositions
```

i.e. "how much has evidence narrowed this trait relative to the prior". Below
`low_confidence_threshold` (0.35) the UI renders "still learning" rather than a number, and the
MCDA still uses the (wide) posterior — which naturally produces `UNCERTAIN` decisions.

---

## 6. Relationship to `TwinVersion`

The authoritative current trait vector is `TwinVersion.trait_snapshot` of the latest version
(JSONB: `{weights: {factor: {mu, sigma}}, dispositions: {id: {alpha, beta}}, gauge: ...}`). A
new `TwinVersion` is appended when the Evolution delta test (spec later) finds a material move.
The *sequence* of snapshots reconstructed from event replay is what powers the Evolution
timeline and Counterfactual Replay — and it is exact, because the update step is deterministic.

---

## 7. What this model deliberately cannot do (state it plainly)

- No cross-trait covariance (v1 diagonal Σ) → it will miss that risk-aversion and
  stability-preference move together. Documented; low-rank Σ is a v2 candidate.
- No population pooling → a brand-new twin is *only* its priors + its own answers; it cannot
  borrow strength from other users (deliberate, ADR-005/008).
- Dispositions are weakly identified from decisions alone; they lean heavily on the interview.
- The Laplace approximation degrades for very few, highly-separating answers → a `σ` floor and a
  property test guard against over-confident collapse.
