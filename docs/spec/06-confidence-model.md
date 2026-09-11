# 06 — Confidence Model

Status: **accepted (Phase 0)** · Implements: ADR-006 · Consumes: spec §04 (posteriors), §05 (score, margin, coverage), ADR-007 (ensemble)

---

## 1. The two quantities — never conflate

| | **Decision score `S`** | **Model confidence `C`** |
|---|---|---|
| Answers | "Which way do the preferences point, how strongly?" | "How much should anyone trust *this* answer?" |
| Range | `[−1, 1]`, **signed** | `[0, 1]`, **unsigned** |
| Produced by | spec §05 weighted-additive MCDA | this document |
| Driven by | factor levels × twin weights | evidence behind those weights · twin agreement · track record · extraction quality · margin |
| Code | `DecisionResult.score: float` (signed) | `Confidence.value: float` + `Confidence.inputs: ConfidenceInputs` |
| High while the other is low? | Yes: `S = 0.7, C = 0.3` → rendered **UNCERTAIN** (strong lean, thin evidence) | Yes: `C = 0.8, S = 0.05` → rendered **UNCERTAIN** (well-evidenced near-tie) |
| Forbidden | narrated by an LLM | narrated by an LLM; **`C == abs(S)`** (a lint/grep + a test guard against this) |

A response DTO exposes both, with distinct names and sign constraints
(`tests/api/test_score_confidence_distinct.py`).

---

## 2. Critical review of the dossier's formula

Dossier draft:
`c = w1·evidence_sufficiency + w2·(1 − ensemble_disagreement) + w3·historical_calibration +
w4·(1 − extraction_entropy)`, with margin as a separate hard gate and "weights tuned against the
prediction ledger".

Problems and fixes:

| Problem | Fix in this spec |
|---|---|
| **Margin only gated, not graded.** A decision at `S = 0.205` (barely clears `TAU_ACCEPT`) would score full confidence. | Add `margin_adequacy` as a graded 5th term; keep the score-band as the *label* rule (spec §05 §5). |
| **Interior weights can't be "tuned against the ledger" at launch** — there is no ledger. Fitting 5 interior weights on <30 points would overfit. | Weights `a…e` are **fixed, documented priors**. What gets recalibrated once data exists is the **scalar output** via a 2-parameter logistic map (§8) — far more robust with little data. |
| **`ensemble_disagreement` double-jeopardy**: a brand-new twin has near-flat weights → parallel twins nearly identical → fake consensus → inflated `C`. | Degenerate-twin guard (§4.2): when `evidence_sufficiency < 0.25`, cap the `(1 − ensemble_disagreement)` term at `0.5`. |
| **`extraction_entropy` vs `coverage` double-count** — both were really "how much don't we know". | Split cleanly: *missingness* → `coverage` → `evidence_sufficiency`; *within-extraction instability* → `extraction_entropy` (§4.4). |
| **`historical_calibration` undefined for small n.** | Pessimistic prior `HC_PRIOR = 0.5`, Bayesian shrink by sample size, and while `n < N_CAL_MIN` the term is **dropped and the other weights renormalised** (not anchored at a fake 0.5); response carries `calibrated: false` (§4.3, §8). |

---

## 3. Constants (v1, `engines/confidence/config.py`, documented, review-scheduled)

```
A_EVIDENCE      = 0.35     # weight on evidence_sufficiency
B_ENSEMBLE      = 0.20     # weight on (1 - ensemble_disagreement)
C_CALIBRATION   = 0.20     # weight on historical_calibration
D_EXTRACTION    = 0.10     # weight on (1 - extraction_entropy)
E_MARGIN        = 0.15     # weight on margin_adequacy
                           # A+B+C+D+E = 1.00
K_EFF           = 4.0      # effective-sample saturation constant
DISAGREE_NORM   = 0.5      # stdev of parallel-twin scores that maps to disagreement 0.5
LABEL_DISAGREE_PENALTY = 0.25
DEGENERATE_ES_CUTOFF   = 0.25
DEGENERATE_ENSEMBLE_CAP = 0.50
N_CAL_MIN       = 12       # resolved predictions before historical_calibration is used
HC_PRIOR        = 0.50
N_RECAL         = 30       # resolved predictions before the logistic output recalibration is fitted
C_MIN           = 0.35     # label gate (restated from spec §05)
```

Weight rationale (documented so an interviewer can challenge each):
`A` largest — with sparse data, *how much we know* dominates trustworthiness. `B` and `C` equal
— ensemble spread and track record are independent, roughly equally informative once available.
`E` above `D` — a knife-edge decision is a bigger threat to correctness than mildly noisy
extraction. `D` smallest — extraction is usually adequate and its worst case is already caught
by `coverage`.

---

## 4. The five inputs

### 4.1 `evidence_sufficiency` ∈ [0,1]

For each factor `i ∈ K`, the effective sample size behind its weight posterior (spec §04):
`N_eff_i = clamp( σ_prior² / σ_post_i² − 1 , 0 , ∞ )`.
Decision-weighted mean: `N̄ = Σ_{i∈K} w_i · N_eff_i` (`w_i` = the renormalised decision weights,
spec §05 §2c).

```
evidence_sufficiency = coverage^0.5 · ( 1 − exp( −N̄ / K_EFF ) )
```

Saturating in `N̄` (`N̄ = 4 → 0.63`, `N̄ = 12 → 0.95`); `coverage^0.5` gives partial credit for
partial factor coverage (the fatal case is handled by the coverage *gate*, not here).

### 4.2 `ensemble_disagreement` ∈ [0,1]

Parallel twins (ADR-007) produce scores `S_1 … S_N` (`N = 5`, incl. base).

```
dispersion  = clamp( stdev(S_1..S_N) / DISAGREE_NORM , 0 , 1 )
ensemble_disagreement = clamp( dispersion + LABEL_DISAGREE_PENALTY · 𝟙[labels not unanimous] , 0 , 1 )
```

**Degenerate-twin guard.** If `evidence_sufficiency < DEGENERATE_ES_CUTOFF`, then the term
`(1 − ensemble_disagreement)` fed into §5 is `min(1 − ensemble_disagreement,
DEGENERATE_ENSEMBLE_CAP)` — a near-flat twin's fake agreement cannot rescue confidence.

### 4.3 `historical_calibration` ∈ [0,1]

Domain `= decision.category ∈ {career, education, project, purchase, relationship, other}`.
Resolved `(Prediction, Outcome)` pairs in that domain: count `n`.

- `n < N_CAL_MIN` **and** all-domain count `< N_CAL_MIN` → term **omitted** (§5 renormalises `A,B,D,E`); `calibrated = false`.
- `n < N_CAL_MIN` **and** all-domain count `≥ N_CAL_MIN` → use all-domain pairs; `calibrated = "cross_domain"`.
- else use domain pairs; `calibrated = true`.

When used: bin the pairs by `predicted_confidence` into 5 equal-width bins;
`ECE = Σ_b (n_b / n) · |accuracy_b − mean_confidence_b|`;
`raw = 1 − ECE`;
`historical_calibration = ( n · raw + N_CAL_MIN · HC_PRIOR ) / ( n + N_CAL_MIN )`
(shrinks toward `HC_PRIOR` while `n` is small, → `raw` as `n` grows).

### 4.4 `extraction_entropy` ∈ [0,1]

Measures *instability* of the factor extraction, not missingness.

- **Default (fast path):** a single extraction with non-empty `rationale_span` for every `known`
  factor → `extraction_entropy = 0.10` (assume adequate), `extraction_path = "single"`.
- **Self-consistency path** (triggered when `1 − coverage > 0.20`, or any `rationale_span` is
  empty, or `decision.high_stakes = true`): run a second extraction (`temperature ≈ 0.3`). Per
  `known` factor, `agree_i = 1` if levels match, `0.5` if one ordinal step apart, `0` otherwise.
  `extraction_entropy = 1 − Σ_{i∈K} w_i · agree_i`. `extraction_path = "self_consistency"`.
  Second call is logged to `ModelRun`.

### 4.5 `margin_adequacy` ∈ [0,1]

From spec §05 §7: `m = |S| − TAU_ACCEPT`; `margin_adequacy = clamp( m / MARGIN_REF , 0 , 1 )`.
For UNCERTAIN-by-band decisions `m < 0` → `margin_adequacy = 0`.

---

## 5. Combination

```
terms = {
  A_EVIDENCE     : evidence_sufficiency,
  B_ENSEMBLE     : ensemble_term,              # (1 - ensemble_disagreement), post degenerate guard
  C_CALIBRATION  : historical_calibration,     # omitted if calibrated == false
  D_EXTRACTION   : 1 − extraction_entropy,
  E_MARGIN       : margin_adequacy,
}
# drop omitted terms, renormalise the remaining weights to sum to 1
raw_C = Σ  weight_k' · value_k
raw_C = clamp(raw_C, 0, 1)
```

## 6. Reported confidence & credible interval

- If a logistic recalibration is active (§8): `C = σ(α + β · raw_C)`, `calibrated_output = true`.
- Else `C = raw_C`, `calibrated_output = false`.
- **Credible interval** on `C`: propagate the trait posteriors — draw `R = 256` seeded samples of
  the weight/disposition posteriors, re-run §05 + §4 for each, take the central 90% of the
  resulting `C` values. Deterministic (fixed seed). Reported as `credible_interval: {low, high}`.
  (This is the only place Monte Carlo is used; it is offline-reproducible and bounded.)

## 7. Label gate (restated)

`C < C_MIN` ⇒ `label = UNCERTAIN`, `uncertain_reason = low_model_confidence` (unless an
earlier-priority reason — `score_in_band`, `insufficient_coverage` — already applied; spec §05 §5).

## 8. Output recalibration (once data exists)

When global resolved-prediction count `≥ N_RECAL`: `notebooks/confidence_calibration.ipynb`
fits `P(correct) = σ(α + β · raw_C)` (Platt scaling) on a train split, checks a reliability
diagram + Brier on a held-out split, and — on human review — the `(α, β)` pair plus a bumped
`CONFIDENCE_VERSION` are committed to `engines/confidence/config.py`. The change is logged like
any engine version bump. Before that point the Report Card shows raw `C` and states
"confidence not yet calibrated (n / N_RECAL)".

## 9. `ConfidenceInputs` — the audit object

Every `Prediction` stores the full `Confidence` object:

```
Confidence:
  value: float                       # C, reported
  raw: float                         # raw_C, pre-recalibration
  calibrated_output: bool
  credible_interval: {low, high}
  inputs:
    evidence_sufficiency: float
    n_bar: float
    coverage: float
    ensemble_disagreement: float
    ensemble_term_capped: bool       # did the degenerate guard fire
    historical_calibration: float | null
    calibrated: bool | "cross_domain"
    calibration_n: int
    extraction_entropy: float
    extraction_path: "single" | "self_consistency"
    margin_adequacy: float
    margin: float
  weights_used: {A,B,C,D,E after renorm}
  confidence_version: str
```

The UI's "how was this confidence computed?" panel renders this object directly. Nothing in it
is LLM-derived.

## 10. Tests (`tests/unit/confidence/`, `tests/property/`)

- Each input function: extreme-value + monotonicity (`test_evidence_sufficiency_saturates`,
  `test_disagreement_lowers_confidence`, `test_margin_adequacy_zero_in_band`,
  `test_degenerate_twin_guard_caps_ensemble_term`).
- `historical_calibration` shrink: `n = 0 → term omitted`; `n = N_CAL_MIN → halfway to raw`;
  `n → large → raw`.
- Combination: weights renormalise correctly when `C` term omitted; `raw_C ∈ [0,1]` always.
- **Distinctness:** `C` never equals `abs(S)` for the golden examples; sign/type constraints on
  the DTO.
- Determinism: same inputs + `CONFIDENCE_VERSION` ⇒ identical `C` and identical credible
  interval (seeded MC).
- Golden: `C` and its `inputs` for MCDA examples 1–5 (spec §05) are pinned in
  `tests/golden/data/confidence_examples/`.
