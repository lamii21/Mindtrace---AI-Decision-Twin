# ADR-007 — Parallel twin architecture

Status: **accepted** · Date: 2026-09-09 · Related: ADR-002, ADR-006

## Context

"Parallel YOU" (Career / Safe / Dream / Future) is the feature most at risk of looking like four
system prompts in a trench coat. It has to be a *real* method with an engineering payoff, or it
should be cut. The dossier's insight — that the **spread between the twins is an uncertainty
signal** — is only valid if the twins are genuinely different *models*, not different personas.

## Decision

The parallel twins are **N deterministic re-parametrisations of the same MCDA engine**, differing
only in their `WeightVector`. No twin has a different prompt, a different code path, or an LLM
personality. Concretely:

- The **base twin** weights `w★` come from the user's trait posteriors (ADR-005).
- Each parallel twin `t` applies a **named, fixed transform** `f_t` to `w★`: a bounded shift
  that up-weights a declared subset of factors and down-weights others, then renormalises. The
  transforms are declared data (`schema/twins.yaml`), versioned, and identical across users:
  - **Career You** — ↑ `growth`, `skill_building`, `option_value`; ↓ `convenience`, `stability`.
  - **Safe You** — ↑ `financial_security`, `stability`, `downside_protection`; ↓ `risk`, `novelty`.
  - **Dream You** — ↑ `intrinsic_interest`, `creative_expression`, `meaning`; ↓ `financial_security`.
  - **Future You** — a lower time-discount: ↑ `long_term_value`, `option_value`, `compounding`;
    the *shift magnitude scales with the decision's stated horizon*.
- The shift is **anchored to the user**: `w_t = renorm(w★ · (1 + λ · shift_t))` with small `λ`
  (v1 `λ = 0.35`). So Career-You of a stability-loving person is still noticeably stability-
  leaning — it is *that person's* career-oriented self, not an archetype.
- `engines/simulation/parallel.py` runs `decide()` once per twin over the same extracted
  factors. Output: per-twin `DecisionResult`, plus:
  - `ensemble_disagreement` = normalised dispersion of the twins' scores `S_t` (feeds ADR-006),
  - `label_consensus` ∈ {unanimous, majority, split},
  - `conflict_axis` = the factor(s) contributing most to the variance across twins
    (deterministic: the factor whose per-twin contribution has the highest variance).
- `engines/simulation` → `engines/debate/synthesis.py` produces the final recommendation:
  a weight-of-evidence vote (base twin counts double), the `conflict_axis`, and the margin.
  The **debate *prose*** is optional and goes through the constrained `verbalize` path (ADR-003
  rule 4): one line per twin, each citing a real contribution and an evidence ID.

`λ`, the number of twins, and the transforms are v1 constants; a study of "does ensemble spread
predict prediction error" lives in `notebooks/` and may retune `λ` (logged, versioned).

## Alternatives considered

1. **Four LLM personas** each asked to judge the decision, then aggregate their verdicts.
2. **One twin only**; drop the feature.
3. **Bootstrap ensemble**: resample the user's decisions, refit weights, get a distribution of
   twins.
4. **Fixed archetype twins** not anchored to the user (`λ` effectively 1, ignore `w★`).
5. **MC-dropout-style perturbation**: add noise to `w★` many times, run MCDA, take the spread.

## Why rejected

1. Personas: non-deterministic, unfalsifiable, the exact "GPT wrapper" failure. The "debate"
   becomes creative writing and the spread means nothing.
2. Dropping it loses a genuine, cheap uncertainty signal and the most visually compelling
   screen. The method below is honest, so keep it.
3. Bootstrap is the *statistically* right ensemble but needs enough decisions to resample
   meaningfully (we have ≤ 40) and produces twins with no interpretable label — you can't call
   one "Safe You". It's a good v2 once data grows; the named transforms are the v1 stand-in and
   are also independently *useful* to the user (they answer "what if I cared more about X").
4. Un-anchored archetypes stop being "you" — they're four generic value profiles, which is a
   weaker product and a weaker uncertainty estimate (the spread would be dominated by the fixed
   transforms, not by the user's own ambiguity).
5. MC-dropout perturbation *is* retained — as a **complementary** input to `evidence_
   sufficiency`/CI width, not as the named twins. The named transforms give interpretability;
   random perturbation gives a smoother uncertainty estimate. v1 ships the named transforms;
   perturbation is a fast-follow.

## Consequences

**Positive**
- Fully deterministic and unit-testable: `test_parallel_twins_are_distinct`,
  `test_career_you_still_reflects_user`, `test_disagreement_monotonic_in_lambda`,
  `test_conflict_axis_matches_hand_computed`.
- The debate screen renders real numbers; the prose is decoration that can be turned off with no
  loss of substance.
- `ensemble_disagreement` gives ADR-006 a second, independent handle on uncertainty beyond the
  posteriors.

**Negative / costs**
- `λ` and the transform tables are hand-designed value judgements. Mitigation: they're declared
  data, versioned, and explicitly "designed, pending empirical study" — not presented as learned.
- Runs the MCDA engine N× per simulation (N=5 incl. base). Trivial cost (microseconds); N is
  capped.
- If `w★` is near-degenerate (brand-new twin, flat weights) the parallel twins are nearly
  identical and the spread is uninformative — which correctly yields low `C` via
  `evidence_sufficiency` anyway. Documented, not a bug.
