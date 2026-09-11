# ADR-005 — Bayesian preference estimation

Status: **accepted** · Date: 2026-09-09 · Related: ADR-002, ADR-006

## Context

The twin's `WeightVector` over factors must be *learned* from a person who supplies very little
data: a 20–30 item forced-choice interview plus, over time, 15–40 observed decisions. Any method
that reports a point estimate without an uncertainty band will overclaim — and the product's
credibility depends on saying "I don't know yet" honestly (principle 16). We need per-trait
uncertainty that (a) starts wide, (b) narrows only as evidence accrues, (c) feeds the confidence
model (ADR-006) and the `UNCERTAIN` gate.

## Decision

Each trait (≈ the importance weight the person places on a factor, plus a few cross-factor
dispositions like `risk_tolerance`) is represented as a **probability distribution, updated by
Bayes' rule**, specified in [`docs/spec/06`](../spec/06-confidence-model.md) and
[`spec/04`](../spec/04-trait-model.md):

- **Representation.** Importance weights `w_i` are modelled on a logit scale with an independent
  **Normal** posterior per trait: `θ_i ~ N(μ_i, σ_i²)`, `w_i = softmax(θ)_i` at read time.
  Bounded [0,1] traits (e.g. `risk_tolerance`) use a **Beta** posterior. Independence across
  traits is an explicit v1 simplification (no full covariance).
- **Prior.** From `traits.yaml`: a weakly-informative population prior (`μ_i = 0`, `σ_i` large)
  optionally shifted by self-declared importance ratings, but with `σ` kept wide so declarations
  don't masquerade as strong evidence.
- **Likelihood.**
  - *Interview answer* (A preferred to B): a logistic (Bradley–Terry / Thurstone) link —
    `P(A≻B | θ) = σ(Σ θ_i (n_iᴬ − n_iᴮ) / s)`. Conjugacy is unavailable, so we update with a
    small, deterministic **Laplace approximation** (Newton step to the MAP + Hessian → new
    `N(μ,σ²)`), or an assumed-density filter. Seeded, fixed iteration count → reproducible.
  - *Observed decision* (chose option k among options): same logistic link over the option's
    normalised factor vector; the observation is "k maximised the person's value function".
- **Posterior read.** `value = μ` (mapped through softmax / logistic), `confidence` derived from
  `σ` and the effective sample size, `credible_interval` = central 90% of the marginal.
- **Determinism.** No MCMC in the request path. Updates are closed-form or fixed-step numeric
  with a fixed seed and tolerance; `engines/preference/update.py` is unit-tested against
  analytically tractable cases (pure-Gaussian, single Beta update).

Full conjoint / hierarchical Bayes (partial pooling across users) is explicitly **out of scope
for v1** and noted as a future study.

## Alternatives considered

1. **Point estimate** via logistic regression / MLE on the interview + decisions.
2. **Full Bayesian with MCMC** (PyMC / NumPyro), sampled per update.
3. **Hierarchical Bayes with cross-user partial pooling** (proper conjoint analysis).
4. **Online gradient methods** (SGD on a Bradley–Terry loss) with a heuristic confidence.
5. **Rule-based scoring** of interview answers into fixed weight buckets, no model.

## Why rejected

1. MLE on ≤ 60 observations for ~12 parameters is high-variance and gives no principled
   uncertainty; you'd bolt on a fake confidence — the exact anti-pattern of principle 2.
2. MCMC per update is non-deterministic (or slow if seeded and long enough to be stable),
   hard to make bit-reproducible across platforms, and overkill for a unimodal low-dimensional
   posterior. Reproducibility (principle) and latency both suffer.
3. Cross-user pooling needs a user base we don't have and introduces one person's data
   influencing another's twin — a privacy and framing problem (ADR-008). Deferred.
4. SGD gives no real posterior; "confidence = 1/(1+steps)" style heuristics are indefensible in
   an interview.
5. Rule-based buckets can't narrow with evidence, can't express uncertainty, and can't ingest
   observed decisions. Fails the core requirement.

## Consequences

**Positive**
- Uncertainty is first-class and honest: a twin with 3 interview answers has wide CIs → most
  decisions land `UNCERTAIN`, which is *correct behaviour*, not a bug.
- Laplace update is ~10 lines of numpy, deterministic, and testable against Gaussian conjugate
  results.
- The Evolution Engine reads the sequence of posteriors straight from event replay.
- Feeds ADR-006 cleanly: `evidence_sufficiency` = f(effective sample size), and posterior `σ`
  directly widens the decision's credible interval.

**Negative / costs**
- **Independence assumption** across traits is wrong in reality (risk aversion correlates with
  stability preference). v1 accepts marginal independence and documents it; a block-diagonal or
  low-rank covariance is a v2 candidate. This is called out in PHASE-0-REVIEW.
- Laplace approximation is poor if a posterior is far from Gaussian (few, highly-separating
  answers). Mitigation: floor on `σ`, and a property test that CIs never collapse below a
  minimum before N_eff crosses a threshold.
- The logit/softmax link makes individual `μ_i` non-identifiable up to a constant; we fix the
  gauge (mean-zero `θ`) and only ever interpret *relative* weights. Documented in spec §04.
- Choosing the logistic scale `s` and prior `σ` is a modelling decision with real effect; fixed
  in `traits.yaml v1`, sensitivity studied in `notebooks/confidence_calibration.ipynb`.
