# 05 — MCDA Mathematics

Status: **accepted (Phase 0)** · Implements: ADR-002 · Uses: [`schema/factors.yaml`](../../schema/factors.yaml), [`schema/traits.yaml`](../../schema/traits.yaml)

This is the formal, frozen specification of the decision function. `engines/mcda/` implements it
exactly; the five worked examples in §9 become `tests/golden/data/mcda_examples/*.json` and
`tests/property/test_mcda.py`. Any change here is an ADR-level event.

---

## 0. Notation & v1 constants

| Symbol | Meaning |
|---|---|
| `F` | the 16 core factor ids (extended factors excluded from aggregation in v1) |
| `A` | the option under consideration ("take the opportunity") |
| `B` | the baseline / status-quo option ("don't") |
| `level_i(o) ∈ {very_low,…,very_high}` | extracted ordinal level of factor `i` for option `o` |
| `known_i(o) ∈ {true,false}` | whether the extractor could place factor `i` for option `o` |
| `a_i(o) ∈ [0,1]` | raw anchor of `level_i(o)` from `factors.yaml` |
| `n_i(o) ∈ [0,1]` | normalised, polarity-corrected, curve-shaped value — **higher is always better** |
| `θ`, `w_i^raw` | twin trait logits and their softmax weights (`traits.yaml`) |
| `w_i^adj`, `w_i` | disposition-adjusted weight, and known-set-renormalised weight |
| `K` | `{ i ∈ F : known_i(A) }` — the known set for this decision |
| `coverage ∈ [0,1]` | share of total adjusted weight that lands on `K` |
| `V(o) ∈ [0,1]` | aggregate value of option `o` |
| `S ∈ [−1,1]` | decision score |
| `c_i` | signed contribution of factor `i` to `S` |
| `m` | decision margin |

**v1 constants** (`engines/mcda/config.py`, documented, not secret, scheduled for empirical
review against the prediction ledger — never silently tuned):

```
TAU_ACCEPT       = 0.20      # S >= TAU_ACCEPT  -> candidate ACCEPT
TAU_REJECT       = -0.20     # S <= TAU_REJECT  -> candidate REJECT   (symmetric)
COVERAGE_MIN     = 0.55      # per-user: + 0.15 * ambiguity_aversion
C_MIN            = 0.35      # ADR-006 model-confidence floor
MARGIN_REF       = 0.10      # reference margin for confidence's margin_adequacy term
SCORE_SCALE      = 2.0       # maps V-difference into [-1,1]
BASELINE_N       = 0.5       # default n_i(B) when the status quo is not described
K_RISK           = 1.7       # risk_tolerance curve base
K_EFFORT         = 1.6       # effort_tolerance curve base
```

---

## 1. Factor normalisation

For each `i ∈ F` with `known_i(o) = true`:

**1a. Anchor.** `a_i(o) = Anchor(level_i(o))` using factor `i`'s `anchors:` if present, else
`scale.default_anchors`. (`financial_return` and `downside_risk` define their own.)

**1b. Disposition curve shaping.** Applied to the raw anchor, *before* polarity correction, only
for the curve-shaped factors:

| factor | exponent `γ_i` |
|---|---|
| `downside_risk`, `financial_security` | `γ = K_RISK ^ (2·risk_tolerance − 1)` |
| `time_demand` | `γ = K_EFFORT ^ (2·effort_tolerance − 1)` |
| all others | `γ = 1` |

`s_i(o) = a_i(o) ^ γ_i`  (with `risk_tolerance = effort_tolerance = 0.5 ⇒ γ = 1 ⇒ s = a`).

**1c. Polarity correction** using `direction` from `factors.yaml`:

```
n_i(o) = s_i(o)             if direction(i) = benefit
n_i(o) = 1 − s_i(o)         if direction(i) = cost      (time_demand, downside_risk)
```

Result: `n_i(o) ∈ [0,1]`, and a larger `n` is better for every factor uniformly.

**1d. Baseline.** If `B` is not described in the input, `n_i(B) = BASELINE_N = 0.5` for all `i`.
If the input describes the status quo, `B` is extracted and normalised identically to `A`.

---

## 2. Weight normalisation

**2a. Raw weights.** `w_i^raw = softmax(θ)_i` over all 16 core factors, `θ` from the latest
`TwinVersion.trait_snapshot` (`traits.yaml` §1). `Σ_{i∈F} w_i^raw = 1`.

**2b. Disposition weight adjustment.**

```
w_i^adj = w_i^raw
        · (1 − 0.6·time_discount)            if i ∈ {option_value, long_term_value}
        · (1 + 0.4·ambiguity_aversion)       if i = reversibility
```

Let `W_adj = Σ_{i∈F} w_i^adj` (≈ 1, shifted slightly by the adjustments).

**2c. Known-set renormalisation.**

```
coverage = ( Σ_{i∈K} w_i^adj ) / W_adj
w_i      = w_i^adj / Σ_{j∈K} w_j^adj        for i ∈ K
w_i      = 0                                 for i ∉ K
```

so `Σ_{i∈K} w_i = 1`. `coverage` is retained for the gate (§5) and for `evidence_sufficiency`
(spec §06).

---

## 3. Aggregate value

Weighted-additive value function (ADR-002):

```
V(o) = Σ_{i∈K} w_i · n_i(o)          ∈ [0,1]
```

---

## 4. Decision score

```
S = clamp( SCORE_SCALE · ( V(A) − V(B) ),  −1,  +1 )
```

With the default neutral baseline, `V(B) = 0.5` and `S = clamp(2·V(A) − 1, −1, 1)`.

---

## 5. Decision rule

```
raw_label =
    ACCEPT      if S ≥ TAU_ACCEPT
    REJECT      if S ≤ TAU_REJECT
    UNCERTAIN   otherwise                       # "dead zone": TAU_REJECT < S < TAU_ACCEPT

COVERAGE_MIN_user = COVERAGE_MIN + 0.15 · ambiguity_aversion

label =
    UNCERTAIN   if coverage < COVERAGE_MIN_user           # reason = insufficient_coverage
    UNCERTAIN   if C < C_MIN                               # reason = low_model_confidence  (C from spec §06)
    raw_label   otherwise
```

The **UNCERTAIN threshold** is therefore three-part: the score band `(TAU_REJECT, TAU_ACCEPT)`,
the coverage gate, and the model-confidence gate. The recorded `uncertain_reason ∈
{score_in_band, insufficient_coverage, low_model_confidence}` (first that applies, in that
priority order) — this distinction is surfaced to the user and drives whether the UI offers
Active Elicitation (for `insufficient_coverage`) or shows the near-tie trade-off (for
`score_in_band`).

---

## 6. Factor contributions

```
c_i = SCORE_SCALE · w_i · ( n_i(A) − n_i(B) )        for i ∈ K
```

Identity (pre-clamp): `Σ_{i∈K} c_i = S`. Reported to the UI as signed shares:

```
c_i%  = 100 · c_i / Σ_{j∈K} |c_j|        →  Σ |c_i%| = 100 ,  sign(Σ c_i%) = sign(S)
```

This is the "Career growth +38.9%" number in the trace. It is *defined here*, never produced by
an LLM.

---

## 7. Decision margin

```
m = |S| − TAU_ACCEPT
```

`m ≥ 0` → `S` is outside the dead zone by `m`; `m < 0` → `S` is inside it. `m` is **not** an
independent gate (the rule in §5 already uses the band); it is reported for display and consumed
by `margin_adequacy = clamp(m / MARGIN_REF, 0, 1)` in the confidence model (spec §06).

---

## 8. Multi-option decisions (supported, minimal)

If the decision genuinely has options `{o_1,…,o_m}`, `m ≥ 3`, and no natural status quo:
compute `V(o_k)` for each; let `V_(1) ≥ V_(2) ≥ …`. Then
`S = clamp(SCORE_SCALE·(V_(1) − V_(2)), −1, 1)`, `label = PICK(o_(1))` if `S ≥ TAU_ACCEPT` and
`coverage`/`C` gates pass, else `UNCERTAIN`. There is no `REJECT` in the multi-option case.
Contributions are computed for `o_(1)` vs `o_(2)`. v1 UI focuses on the binary case; multi-option
is exercised by one golden test only.

---

## 9. Hand-worked examples

All examples 1–4 use one **reference twin `T-ref`** (dispositions:
`risk_tolerance = 0.35`, `time_discount = 0.5`, `ambiguity_aversion = 0.5`,
`effort_tolerance = 0.5`). Curve exponent for risk-shaped factors:
`γ = 1.7^(2·0.35 − 1) = 1.7^(−0.30) ≈ 0.853`.

`T-ref` raw softmax weights `w^raw` (the 6–7 active factors shown; the remaining factors carry
the residual and are `known=false` in every example, so they never enter aggregation):

| factor | `w^raw` |
|---|---|
| skill_growth | 0.22 |
| financial_return | 0.16 |
| downside_risk | 0.14 |
| financial_security | 0.10 |
| location_fit | 0.10 |
| intrinsic_interest | 0.10 |
| autonomy | 0.08 |
| stability | 0.06 |
| social_fit | 0.06 |
| reversibility | 0.05 |
| (residual, 6 factors) | 0.03 total |

No disposition weight adjustments fire in examples 1–3 (no `option_value`/`long_term_value`/
`reversibility` in `K`); example 4 uses the `reversibility` bump.

---

### Example 1 — clear ACCEPT

**Situation.** "Backend internship. Pays 1400 €/mo, uses the stack I want to learn, established
company with a strong completion record, in my city."

**Extraction (option A).** `known` for 6 factors:

| factor | level | `a` | `n` |
|---|---|---|---|
| skill_growth | very_high | 1.00 | 1.000 |
| financial_return | high | 0.72 | 0.720 |
| financial_security | high | 0.75 | `0.75^0.853 =` 0.782 |
| downside_risk (cost) | low | 0.20 | `1 − 0.20^0.853 =` 0.747 |
| location_fit | very_high | 1.00 | 1.000 |
| intrinsic_interest | high | 0.75 | 0.750 |

**Weights.** `Σ_{K} w^raw = 0.22+0.16+0.10+0.14+0.10+0.10 = 0.82`.
`coverage = 0.82/1.00 = 0.82` ≥ `COVERAGE_MIN_user = 0.55 + 0.15·0.5 = 0.625`. ✓
Renormalised `w`: skill_growth 0.2683, financial_return 0.1951, financial_security 0.1220,
downside_risk 0.1707, location_fit 0.1220, intrinsic_interest 0.1220.

**Aggregate.** `V(A) = 0.2683·1.000 + 0.1951·0.720 + 0.1220·0.782 + 0.1707·0.747 +
0.1220·1.000 + 0.1220·0.750 = 0.8451`.
`S = clamp(2·(0.8451 − 0.5)) = 0.690`.

**Result.** `S = 0.690 ≥ 0.20` → **ACCEPT**. `m = 0.690 − 0.20 = 0.490`.
Contributions (%): skill_growth **+38.9**, location_fit +17.7, financial_return +12.4,
downside_risk +12.2, financial_security +10.0, intrinsic_interest +8.8. (Σ = +100.)

---

### Example 2 — clear REJECT

**Situation.** "Unpaid 6-month role, I'd have to quit my current job and move away from family,
the company might fold within a year, and I wouldn't learn much new."

**Extraction (A).**

| factor | level | `a` | `n` |
|---|---|---|---|
| financial_return | very_low | 0.00 | 0.000 |
| financial_security | very_low | 0.00 | `0^0.853 =` 0.000 |
| downside_risk (cost) | very_high | 1.00 | `1 − 1^0.853 =` 0.000 |
| location_fit | very_low | 0.00 | 0.000 |
| stability | very_low | 0.00 | 0.000 |
| skill_growth | low | 0.25 | 0.250 |

**Weights.** `Σ_K w^raw = 0.16+0.10+0.14+0.10+0.06+0.22 = 0.78`. `coverage = 0.78` ≥ 0.625 ✓.
Renormalised: financial_return 0.2051, financial_security 0.1282, downside_risk 0.1795,
location_fit 0.1282, stability 0.0769, skill_growth 0.2821.

**Aggregate.** `V(A) = 0.2821·0.250 = 0.0705` (all other `n = 0`).
`S = clamp(2·(0.0705 − 0.5)) = −0.859`.

**Result.** `S = −0.859 ≤ −0.20` → **REJECT**. `m = 0.859 − 0.20 = 0.659`.
Contributions (%): financial_return **−23.9**, downside_risk −20.9, skill_growth −16.4,
financial_security −14.9, location_fit −14.9, stability −9.0. (Σ = −100.)

---

### Example 3 — near tie → UNCERTAIN (`score_in_band`)

**Situation.** "A contract role: better pay and more learning than my current job, but a rough
commute, a team I'm lukewarm on, and moderate risk."

**Extraction (A).**

| factor | level | `a` | `n` |
|---|---|---|---|
| financial_return | high | 0.72 | 0.720 |
| skill_growth | high | 0.75 | 0.750 |
| location_fit | low | 0.25 | 0.250 |
| social_fit | low | 0.25 | 0.250 |
| downside_risk (cost) | moderate | 0.45 | `1 − 0.45^0.853 =` 0.494 |
| intrinsic_interest | moderate | 0.50 | 0.500 |

**Weights.** `Σ_K w^raw = 0.16+0.22+0.10+0.06+0.14+0.10 = 0.78`. `coverage = 0.78` ≥ 0.625 ✓.
Renormalised: financial_return 0.2051, skill_growth 0.2821, location_fit 0.1282,
social_fit 0.0769, downside_risk 0.1795, intrinsic_interest 0.1282.

**Aggregate.** `V(A) = 0.2051·0.720 + 0.2821·0.750 + 0.1282·0.250 + 0.0769·0.250 +
0.1795·0.494 + 0.1282·0.500 = 0.5633`.
`S = clamp(2·(0.5633 − 0.5)) = 0.127`.

**Result.** `−0.20 < 0.127 < 0.20` → **UNCERTAIN**, `uncertain_reason = score_in_band`.
`m = 0.127 − 0.20 = −0.073` (inside dead zone).
Contributions (%): skill_growth +42.0, financial_return +26.8, location_fit −19.1,
social_fit −11.5, downside_risk −0.7, intrinsic_interest 0.0. Signed sum +37.6 (positive lean
toward ACCEPT, not enough to clear the band). The UI shows the trade-off, **not** an Active
Elicitation prompt (coverage is fine).

---

### Example 4 — conflicting factors, resolves to ACCEPT at low margin

**Situation.** "A startup offer: huge learning, full autonomy, work I'd love — but a real pay
cut, thin financial safety, and a genuine chance it fails in a year. I could return to a similar
job if it did."

**Extraction (A).**

| factor | level | `a` | `n` |
|---|---|---|---|
| skill_growth | very_high | 1.00 | 1.000 |
| autonomy | very_high | 1.00 | 1.000 |
| intrinsic_interest | very_high | 1.00 | 1.000 |
| financial_return | low | 0.30 | 0.300 |
| financial_security | low | 0.25 | `0.25^0.853 =` 0.306 |
| downside_risk (cost) | high | 0.75 | `1 − 0.75^0.853 =` 0.218 |
| reversibility | very_high | 1.00 | 1.000 |

**Weights.** `w_reversibility^adj = 0.05·(1 + 0.4·0.5) = 0.06`; `W_adj = 1.00 + 0.01 = 1.01`.
`Σ_K w^adj = 0.22+0.08+0.10+0.16+0.10+0.14+0.06 = 0.86`.
`coverage = 0.86/1.01 = 0.851` ≥ 0.625 ✓.
Renormalised `w` (÷0.86): skill_growth 0.2558, autonomy 0.0930, intrinsic_interest 0.1163,
financial_return 0.1860, financial_security 0.1163, downside_risk 0.1628, reversibility 0.0698.

**Aggregate.** `V(A) = 0.2558·1 + 0.0930·1 + 0.1163·1 + 0.1860·0.300 + 0.1163·0.306 +
0.1628·0.218 + 0.0698·1 = 0.6617`.
`S = clamp(2·(0.6617 − 0.5)) = 0.323`.

**Result.** `S = 0.323 ≥ 0.20` → **ACCEPT**, `m = 0.123` (low). `label_consensus` across parallel
twins will likely be `majority`, not `unanimous` (Safe You flips) → this is the canonical
"what would flip this?" case: dropping `reversibility` to `low` gives `S ≈ 0.18` → UNCERTAIN.
Contributions (%): skill_growth +34.3, autonomy +12.5, intrinsic_interest +15.6,
reversibility +9.4, financial_return −10.0, financial_security −6.0, downside_risk −12.3.

---

### Example 5 — insufficient evidence → UNCERTAIN (`insufficient_coverage`)

**Situation.** "I got offered a role at a company. Not sure of the details yet — should I take
it?"

**Extraction (A).** The extractor can place only 2 factors with `known = true`:

| factor | level | `a` | `n` |
|---|---|---|---|
| intrinsic_interest | moderate | 0.50 | 0.500 |
| downside_risk (cost) | moderate | 0.45 | 0.494 |

All other 14 factors: `known = false`.

**Weights.** `Σ_K w^raw = 0.10 + 0.14 = 0.24`. `coverage = 0.24 / 1.00 = 0.24`.
`COVERAGE_MIN_user = 0.55 + 0.15·0.5 = 0.625`. `0.24 < 0.625` → gate fires.

**Aggregate (still computed, for the record).** Renormalised: intrinsic_interest 0.4167,
downside_risk 0.5833. `V(A) = 0.4167·0.500 + 0.5833·0.494 = 0.4964`. `S = 2·(0.4964 − 0.5) =
−0.007`.

**Result.** **UNCERTAIN**, `uncertain_reason = insufficient_coverage`, `coverage = 0.24`,
`known_factors = 2/16`, `S ≈ −0.01`. The API returns the Active-Elicitation hook: the
highest-prior unknown factor is `skill_growth` (`w^raw = 0.22`) → "To answer this I need to know
roughly how much this role would grow your skills." No decision is asserted (principle 16).

---

## 10. Properties the implementation must satisfy (→ `tests/property/test_mcda.py`)

1. **Bounds.** `V ∈ [0,1]`, `S ∈ [−1,1]`, `Σ|c_i%| = 100 ± ε`.
2. **Score identity.** `Σ_{i∈K} c_i = S` before clamping (`ε = 1e-9`).
3. **Monotonicity.** Raising `level_i(A)` by one step for a `benefit` factor in `K` never
   decreases `S`; for a `cost` factor never increases `S`. (Holds because `w_i ≥ 0`, curves are
   monotone, polarity is linear.)
4. **Order invariance.** `S` and `{c_i}` are invariant to the order factors are supplied in.
5. **Dead-zone ⇒ UNCERTAIN.** `−0.20 < S < 0.20` ⇒ `label = UNCERTAIN` (absent an earlier gate).
6. **Coverage gate dominates.** `coverage < COVERAGE_MIN_user` ⇒ `UNCERTAIN` regardless of `S`.
7. **Determinism.** Same inputs + `ENGINE_VERSION` ⇒ byte-identical `DecisionResult` across
   runs, processes, and OSes (numpy float64, fixed evaluation order).
8. **Neutral disposition ⇒ no curve.** `risk_tolerance = effort_tolerance = 0.5` ⇒ `n_i = a_i`
   after polarity for all factors (`γ = 1`).
9. **Empty known set.** `K = ∅` ⇒ `coverage = 0` ⇒ `UNCERTAIN / insufficient_coverage`, no
   division by zero.
