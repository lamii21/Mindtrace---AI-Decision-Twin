# Phase 0 — Brutally Honest Review

Status: **living** · Owner: lead AI SWE · Read this before committing to the build.

This is the "argue against the project" document. It is deliberately unkind. Everything here is
a real concern, not a rhetorical hedge.

---

## 1. Decisions that are still genuinely uncertain

| # | Decision | Why it's unresolved | How we'll resolve it |
|---|---|---|---|
| U1 | **16 core factors, or fewer.** | Estimating 16 weights from ≤ 40 decisions + ~20 interview answers is over-parameterised. The posteriors may just stay at the prior. | Phase-1 experiment: run interview-only priors for an 8-factor vs 16-factor taxonomy on the same synthetic users; compare consistency scores and CI widths. Ship whichever is more stable. |
| U2 | **Weighted-additive vs interaction terms.** | `financial_return × financial_security` and `time_demand × health_wellbeing` clearly interact (money matters less above a threshold). v1 hides this in per-factor curves + a disclaimer. | Prototype a 2–3 term bilinear extension in `notebooks/`; adopt only if it measurably improves held-out consistency. Likely v2. |
| U3 | **Named parallel twins vs a bootstrap ensemble.** | Named transforms (`Career You` = +λ·shift) are interpretable but are hand-designed value judgements, not learned. The statistically honest ensemble (resample decisions, refit) needs data we don't have. | Ship named transforms in v1 (also independently useful to the user). Add MC-dropout weight perturbation as a *second* uncertainty input (ADR-007 §consequences). Move to bootstrap when a user has ≥ 60 decisions — which may be never for the target user. |
| U4 | **Confidence weights `a…e` (0.35/0.20/0.20/0.10/0.15).** | Hand-set. The recalibration plan (Platt-scale the scalar output) is sound but unproven until ~30 labelled predictions exist. | Keep fixed; be loud about "uncalibrated"; recalibrate the output, not the interior weights, once data lands. Revisit the split only if the reliability diagram is badly non-monotone in a specific term. |
| U5 | **Disposition → curve-shaping links.** | `risk_tolerance` bending the `downside_risk` normalisation curve is elegant but possibly over-clever. It could just be an extra weight. | A/B in a notebook: curve-shaping vs "risk_tolerance as a 17th weight". Prefer the simpler one if results are comparable (principle 9). |
| U6 | **Status-quo baseline `n_i(B) = 0.5`.** | Strong assumption for the binary case. A person deeply happy with their current situation has a status quo well above neutral. | Where the input describes the current situation, extract `B` properly. Where it doesn't, keep 0.5 but surface it in the trace ("compared to a neutral baseline") and let the user set a "current situation" once, reused across decisions. |
| U7 | **`TwinVersion` explosion.** | "Append a version on every material trait move" could produce dozens of versions in a week of active use. | Add a debounce: at most one `post_decision` version per rolling 72 h unless the delta is large; always allow the weekly `scheduled` snapshot. Tune the "material" threshold against real usage. |
| U8 | **Projection sync → async cutover (M-later).** | Synchronous projection is simple but makes `POST /memories` slow once embeddings + preference updates run inline. Async introduces read-after-write lag the UI must handle. | Stay sync through M9. Cut to async only when a p95 latency budget is actually breached; the API already reserves `202 + job` for it. |
| U9 | **Multi-option decisions.** | Spec §05 §8 handles them minimally. If users routinely enter 3–4 options, the binary framing and the whole `ACCEPT/REJECT` vocabulary strain. | Watch real usage. If multi-option is common, it becomes its own spec revision, not a footnote. |
| U10 | **Local extraction feasibility.** | Embeddings local is settled. Whether a self-hostable model can do `moderate/high`-granularity factor extraction well enough is unknown. | Build the extraction eval set (A2 below) first; test a local model against it before committing either way. |

---

## 2. Assumptions that need external validation (not just a decision)

1. **That the target user logs 15–40 decisions.** Realistically many portfolio users will enter
   3–10. If so, the twin *never leaves "mostly UNCERTAIN"* — which is epistemically correct but
   will read as "the product doesn't work" to a casual viewer or a non-technical interviewer.
   *Mitigations:* (a) make the interview carry real weight; (b) an onboarding **retrospective
   mode** — score 8–12 past decisions with outcomes in one sitting — to bootstrap both the
   posterior and the Evaluation ledger; (c) a clearly-labelled seeded demo persona with a full
   history for demos.
2. **That forced-choice interview answers transfer to real decisions.** Hypothetical bias is a
   well-documented effect in stated-preference research. The Consistency Probe partially checks
   internal consistency, not transfer.
3. **That LLM factor extraction is reliable at this granularity.** Untested. **Deliverable
   before trusting `/simulate`: a hand-labelled eval set of 60–100 real-ish situations with
   gold factor levels**, scored for exact + within-one-step agreement. If agreement is poor, the
   `known` flag / coverage gate is doing more work than the model and the product's honesty
   depends on saying so.
4. **That users record outcomes and satisfaction.** Low compliance ⇒ the Evaluation Engine has
   nothing to show ⇒ the "measurable" claim is hollow. Outcome logging must be one tap from a
   past decision, prompted, and ideally seeded by retrospective mode.
5. **The Laplace approximation is adequate** for the posterior shapes we actually get (few,
   highly-separating answers can be far from Gaussian). Guarded by a `σ` floor + a property
   test; still an approximation.
6. **Preferential independence of factors** (U2) — assumed, known to be imperfect.
7. **That "measures model–data consistency, not psychological truth" survives contact with
   users.** The risk is drift: the disclaimer stays in the docs while the UI copy quietly
   becomes "MINDTRACE understands you". The disclaimer is a fixed string in the API response and
   a test — keep it that way.

---

## 3. Parts of the dossier that are over-engineered

| Dossier element | Verdict | What we did instead |
|---|---|---|
| **Six named "memory stores"** (episodic/semantic/preference/decision/evidence/contradiction) | Half of these aren't memories. | One append-only event log + typed projections. "Evidence" and "Contradiction" are derived structures, modelled as their own tables, not "memory". |
| **3- and 5-year "Talk to Future Me" chat** | Cut. | All generation, no measurement, highest hallucination surface. Kept only a single **1-year conditional scenario**, permanently labelled a simulation. |
| **Rich free-form Twin Debate** | Trimmed hard. | One constrained, evidence-cited line per twin, generated from a pre-computed disagreement object, with a rejection check. The prose is optional; the structured synthesis is the substance. |
| **Neo4j knowledge graph** | Cut (ADR-004). | `evidence` table + recursive CTE. Depth 2–3, one tenant, hundreds of edges. A second datastore would be resume-driven design. |
| **Redis + Celery + background workers as a pillar** | Deferred and shrunk. | `arq` (async-native, ~200 LOC of config), introduced at M10, for ~4 periodic jobs. Not in the correctness path. |
| **Semantic twin versioning `v1.0 → v1.5 → v2.0`** | Cosmetic. | Integer versions + classified deltas. Plus a debounce (U7) so it doesn't explode. |
| **"Twin Activity: 5 new patterns discovered" as a dashboard headline** | Keep, but demote. | A cheap view over `audit_log`. Fine to show; not a pillar. |
| **10 engines shipped in one project** | Unrealistic for one person at portfolio quality. | The 10 milestones stop at a coherent core (memory, MCDA, preference, confidence, interview, deletion, evidence, base + parallel twins). Evolution / full Evaluation / Contradiction are honestly Phase 2+. |

---

## 4. Parts that are genuinely innovative (keep and lead with these)

1. **Re-derivable beliefs from an event log** → deletion *and* explanation are **exact**, not
   best-effort. Rare in practice and technically real (ADR-001, ADR-008).
2. **The strict LLM boundary as an architectural stance** — four functions, import-linter
   enforced, every output schema-validated, no LLM value ever entering a calculation. Most
   "AI products" cannot draw this line on a whiteboard; this one can.
3. **Model confidence as a computed, separately-audited quantity** with an explicit
   recalibration path, kept rigorously distinct from the decision score (`C ≠ abs(S)`, enforced
   by a test). The `ConfidenceInputs` audit object is a strong interview artefact.
4. **Parallel-twin spread as a calibrated uncertainty input** — *because* the twins are one code
   path re-parametrised by a weight vector, not four prompts (ADR-007). This is the difference
   between a real ensemble method and a personality gimmick.
5. **The evaluation harness** — Brier / ECE / reliability diagram + a **paraphrase Consistency
   Probe that needs zero outcome labels** (works from day one). This is the "measurable"
   backbone.
6. **Active Elicitation via expected information gain** over the trait posterior — the twin asks
   the single most informative question instead of guessing (spec §07 §5).
7. **The interview and the decision engine are the same value function** — no train/serve
   mismatch; interview evidence and decision evidence are directly comparable on one scale.

If time forces cuts, cut breadth (engines 8–10), never these seven.

---

## 5. Where MINDTRACE could still look like an AI wrapper if built badly

| Failure mode | The tell | The guard already in the design |
|---|---|---|
| `verbalize` gets latitude and starts adding reasons | The trace explanation says things the numbers don't | Post-check: every sentence maps to a factor/term in the input object; unknown citation → reject; 2 failures → show the structured view, no prose. Ship the structured view first. |
| Confidence tracks `abs(S)` because early inputs are weak | `C` and `|S|` correlate ~1.0 in the demo | Show the `ConfidenceInputs` panel; label "uncalibrated (k/N)"; a test asserts they're never wired to the same source. Accept that early `C` is dominated by evidence/margin — and say so. |
| Extraction is the only thing between text and the answer, and it's unevaluated | Change the wording of a situation, the decision flips, and nobody noticed | The 60–100 item extraction eval (A2·3); `rationale_span` shown in the trace; user-editable factors; the `known` flag + coverage gate; the Consistency Probe. |
| Parallel twins implemented as prompt variants "for speed" | There's a prompt template per twin | One MCDA code path; twins differ only by `WeightVector`; `test_no_prompt_in_parallel_twins`. |
| Demo uses seeded data that isn't labelled as seeded | The twin is suspiciously confident and well-evidenced on day one | Seeded personas are watermarked in the UI and the README; never presented as a real run. |
| `UNCERTAIN` is suppressed to make demos look decisive | The twin always has an answer | `UNCERTAIN` is a first-class output with three distinct reasons surfaced; a test asserts the gates fire; the demo persona deliberately includes an `insufficient_coverage` case. |
| The "not psychological truth" framing quietly disappears | Marketing copy says "knows you" | Fixed disclaimer string in the API + a test; PHASE-0-REVIEW §2·7. |

---

## 6. The five biggest risks to the whole project

1. **Data starvation** → twin stuck at `UNCERTAIN` → reads as broken. *Highest-probability
   failure.* Mitigate with interview weight + retrospective onboarding mode + labelled demo
   persona. If retrospective mode isn't built, the product under-delivers for real users.
2. **No outcome data** → Evaluation Engine is empty → the flagship "measurable" claim is hollow.
   Mitigate: retrospective mode seeds the ledger; a synthetic backtest on the demo persona is
   available for the Report Card screen; make outcome logging one tap.
3. **Unmeasured extraction quality** → silent garbage-in that the deterministic core faithfully
   turns into a confident-looking wrong trace. Mitigate: build the extraction eval in Phase 1
   and gate on it.
4. **Scope** → one person cannot ship 10 engines to portfolio quality. Mitigate: M1–M10 is the
   line. A deep, well-tested core (event sourcing + MCDA + Bayesian preference + confidence +
   evaluation backtest) beats a shallow implementation of everything. Be willing to stop at M9.
5. **Framing drift** → the honest epistemics erode into overclaim under demo pressure. Mitigate:
   the disclaimer and the `C ≠ abs(S)` invariant are code + tests, not guidelines.

---

## 7. Recommended minimum credible scope (if you build nothing else)

**M1–M9**, optionally minus M10's parallel twins, **plus** the extraction eval set and a small
retrospective-onboarding flow that seeds ~10 past decisions with outcomes.

That delivers: an event-sourced, re-derivable memory; a deterministic MCDA decision core with a
full trace; a Bayesian preference model with honest uncertainty; a computed model confidence
distinct from the score; a structured Twin Interview; exact deletion with re-derivation; a
queryable evidence chain; and enough of an evaluation backtest to show a reliability diagram.

That is already a flagship AI-Software-Engineering project and a strong 45-minute interview
conversation. Everything past it (parallel-twin debate, evolution timeline, live evaluation,
active elicitation, "what would flip this") is upside, not the thesis.

---

## 8. M2 addendum — what implementing event sourcing actually surfaced

M2 built the event log, the `Memory`/`Evidence` domain types, the pure fold, and a real
(non-topic-based) deletion preview/apply — see `docs/11-roadmap-milestones.md`'s sequencing note
for how the milestone list was renumbered to match. Four things worth recording rather than
burying in code:

1. **`Evidence.belief_type`'s approved vocabulary has no "a memory corroborates another memory"
   case** (it's `preference`/`trait`/`value`/`decision_factor`/`contradiction` — all M3+ belief
   kinds). M2's evidence tests exercise the mechanism with a synthetic `decision_factor` belief
   id rather than adding a new enum value, since nothing yet needs memory-to-memory evidence as a
   first-class feature. Revisit once M4 (Bayesian preference) produces the first real belief and
   the Evidence Panel design gets a real workout — the gap may turn out to matter, or may not.
2. **`Memory` deliberately omits `confidence`/`salience`/`embedding`** from the AG-3 sketch in
   `docs/architecture/02-domain-model.md` — each needs an engine M2 doesn't have (confidence
   model, ranking, embeddings). Add them when their producing milestone exists, not before;
   populating them with a placeholder now would be exactly the "looks computed but isn't" failure
   principle 15 warns about.
3. **A projected `Memory`'s id is its originating event's id** (`MemoryId(event.id)`), not a
   separately minted one. Clean and fully deterministic for M2. Worth a deliberate check once
   Postgres persistence lands (deferred, unscheduled - see the roadmap note): this makes
   `memory.id` naturally foreign-key-compatible with `memory_event.id`, which is convenient, but
   the schema design should confirm that's still wanted rather than inheriting it by accident.
4. **Deletion is real, not a preview of a preview.** `deleted` events tombstone a memory in place
   (kept, `deleted_at` set - not physically removed) and `preview_deletion`/`apply_deletion`
   compute genuine impact against `Evidence`. What remains out of scope: topic-based ("forget
   everything about location") deletion needs semantic matching over memory content, which needs
   embeddings (M5+) - explicit-id deletion is the whole of M2's claim here, honestly bounded.
