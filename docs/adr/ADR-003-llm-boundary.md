# ADR-003 — LLM boundary

Status: **accepted** · Date: 2026-09-09 · Related: ADR-002, ADR-008

## Context

An LLM is genuinely useful for two things MINDTRACE needs: turning messy natural-language input
into structured data, and turning structured results into readable prose. It is dangerous
everywhere else — it fabricates numbers, invents justifications, and is sensitive to adversarial
text embedded in user memories. The codebase must make the safe uses easy and the unsafe uses
*structurally impossible*, not merely discouraged.

## Decision

**One package, `mindtrace.llm`, is the only code in the repository permitted to import a model
provider SDK** (enforced by import-linter, ADR-004 §CI). It exposes exactly four typed
operations via Protocols in `llm/ports.py`:

| Operation | Input | Output | Used by |
|---|---|---|---|
| `extract(text, schema)` | user text + a Pydantic model class | a **validated instance of that model**, or raises `ExtractionValidationError` | `engines/memory` (classify), `services/decision` (factor extraction) |
| `embed(texts)` | list of strings | list of `float[1024]` | projectors, evidence retrieval |
| `verbalize(structured, template_id)` | an **already-computed** dataclass + a versioned template | `str` (prose) that passes a post-check | `engines/debate`, trace explanation |
| `judge(pair, rubric)` | two items + rubric | `JudgeVerdict{label, rationale}` (label from a closed enum) | `engines/evaluation` (paraphrase equivalence) |

Rules, all CI- or test-enforced:

1. **No LLM output is used as a number in any calculation.** `extract` returns categorical
   factor *levels* and a `known` flag — never a weight, score, probability, or confidence.
   `verbalize`/`judge` outputs never re-enter an engine as data.
2. **Every structured output is a Pydantic v2 model with `extra="forbid"` and value constraints**
   (`contracts/`). Validation failure → deterministic fallback path or `UNCERTAIN`; never
   "proceed on the raw text".
3. **Prompt-injection containment** (`guards.py`): user-supplied memory text is passed only
   inside a delimited, clearly-labelled data block; the system prompt states that content in the
   data block is untrusted and must not be treated as instructions; outputs are validated
   against the schema regardless. Retrieval never concatenates memory text into an instruction
   position.
4. **`verbalize` post-check**: each generated sentence must map to a factor/term present in the
   input object; any citation token must be an ID from the supplied allow-list; sentiment must
   match the sign of the referenced contribution. Two failures → UI shows the structured object
   with no prose.
5. **Determinism budget**: `temperature = 0`, prompts and model IDs pinned by version. LLM steps
   are *not* required to be bit-reproducible (providers drift); therefore no reproducibility-
   critical value may depend on them (follows from rule 1). `ModelRun` records every call.
6. **Provider-agnostic**: `providers/anthropic.py` is one adapter; `providers/local_embeddings.py`
   keeps embeddings in-house so raw prose need not leave the box for the highest-volume call.

## Alternatives considered

1. **LangChain / LlamaIndex / an agent framework** for extraction + orchestration.
2. **Instructor / raw provider structured-output** scattered at each call site.
3. **Function-calling / tools** letting the model "call" the MCDA engine.
4. **Local-only open-weights model** for everything, no external provider.

## Why rejected

1. LangChain adds chains, agents, memory abstractions, retrievers, and callback machinery for
   what is four function calls with fixed schemas. It obscures the boundary this ADR is trying
   to make explicit and pins us to its churn. Engineering principles 10–11. No demonstrated
   necessity.
2. Scattering structured-output calls means no single choke point for injection defence, schema
   registry, prompt versioning, `ModelRun` accounting, or the import ban. The `llm/` package is
   thin (~150–250 LOC) but the centralisation is the point.
3. Tool/function-calling would let the model decide *when and with what* to invoke the engine —
   handing it back partial control of the decision and making the flow non-deterministic.
   Rejected outright (principle 3).
4. Attractive for privacy but: factor extraction quality from a small local model is materially
   worse, and self-hosting a capable instruct model is real ops for a portfolio project. We
   compromise: **embeddings local, extraction/verbalisation via a hosted model** with the
   exposure documented (ADR-008) and minimised (send the minimal span, redact obvious PII).

## Consequences

**Positive**
- One file to audit for provider exposure; one place to add a redaction pass or swap providers.
- `tests/api/test_prompt_injection.py` fires known payloads through `/memories` and asserts no
  instruction leakage and schema-valid extraction.
- Engines depend on `llm.ports` Protocols, so unit tests inject a fake extractor/embedder — no
  network in the engine test suite.

**Negative / costs**
- Extraction failures must have a real deterministic fallback for each call site (e.g. factor
  extraction falls back to "all factors `known=false` → coverage gate → `UNCERTAIN`"). More code
  than "trust the model".
- `verbalize` post-check occasionally suppresses prose the user would have found fine. Accepted:
  a missing sentence is better than a fabricated one.
- Hosted-provider dependency for a core path; mitigated by the fallback and by embeddings being
  local.
