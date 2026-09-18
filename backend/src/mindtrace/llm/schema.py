"""The extraction contract and the typed outcome `extraction.py` always returns.

`RawExtractedFactor`/`RawExtraction` are deliberately taxonomy-*agnostic* -
they only check shape (field types, required-ness, internal `known`/`level`/
`rationale_span` consistency). Cross-checking a `factor_id`/`level` against
the authoritative `FactorTaxonomy` is a separate step
(`mindtrace.llm.validation`), so a taxonomy change never touches this parsing
layer, and "the JSON doesn't even have the right shape" stays a distinct,
separately-testable failure from "the JSON is well-shaped but invents a
factor".
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from mindtrace.domain.decision import FactorVector
from mindtrace.domain.enums import ExtractionFailureType, ExtractionMode
from mindtrace.domain.ids import FactorId

_FrozenModel = ConfigDict(frozen=True, extra="forbid")
_MAX_RATIONALE_SPAN_LENGTH = 240
_MAX_FACTOR_ID_LENGTH = 64


class RawExtractedFactor(BaseModel):
    """One factor exactly as the LLM must emit it.

    `known=True` requires both `level` and a non-empty `rationale_span`;
    `known=False` must carry neither - the same "known implies level" shape
    `mindtrace.domain.decision.FactorReading` already enforces, checked here
    one layer earlier (before a `factor_id`/`level` is even known to be real).
    `known` is a `StrictBool`: pydantic's default *lax* mode would otherwise
    silently coerce the int `1` into `True`, exactly the "repair the model's
    output" M5 §6 forbids.
    """

    model_config = _FrozenModel

    factor_id: str = Field(min_length=1, max_length=_MAX_FACTOR_ID_LENGTH)
    known: StrictBool
    level: str | None = None
    rationale_span: str | None = Field(default=None, max_length=_MAX_RATIONALE_SPAN_LENGTH)

    @model_validator(mode="after")
    def _known_matches_level_and_span(self) -> RawExtractedFactor:
        if self.known:
            if self.level is None:
                msg = "known=true requires a level"
                raise ValueError(msg)
            if not self.rationale_span:
                msg = "known=true requires a non-empty rationale_span"
                raise ValueError(msg)
        else:
            if self.level is not None:
                msg = "known=false must not carry a level"
                raise ValueError(msg)
            if self.rationale_span is not None:
                msg = "known=false must not carry a rationale_span"
                raise ValueError(msg)
        return self


class RawExtraction(BaseModel):
    """The complete raw JSON object the LLM must return for one extraction call."""

    model_config = _FrozenModel

    schema_version: Literal["1"] = "1"
    factors: tuple[RawExtractedFactor, ...]

    @model_validator(mode="after")
    def _no_duplicate_factor_ids(self) -> RawExtraction:
        seen: set[str] = set()
        for factor in self.factors:
            if factor.factor_id in seen:
                msg = f"duplicate factor_id in extraction output: {factor.factor_id!r}"
                raise ValueError(msg)
            seen.add(factor.factor_id)
        return self


class ExtractionMetadata(BaseModel):
    """Provenance for one extraction call (M5 §10): never a mutable "latest"."""

    model_config = _FrozenModel

    factor_schema_version: int
    extraction_schema_version: str
    prompt_version: str
    provider: str
    model: str
    mode: ExtractionMode
    temperature: float = Field(ge=0.0, le=2.0)


class ExtractionOutcome(BaseModel):
    """The extraction boundary's complete, self-contained answer.

    `factors` is **always** present and always a valid `FactorVector` - on
    failure, every core factor is `known=False` (ADR-003's documented
    fallback: coverage collapses to 0, so the MCDA engine's own coverage gate
    reports `UNCERTAIN` - not a fabricated guess, and not a special case the
    engine needs to know about).
    """

    model_config = _FrozenModel

    status: Literal["success", "failed"]
    factors: FactorVector
    metadata: ExtractionMetadata
    failure_type: ExtractionFailureType | None = None
    failure_detail: str | None = None
    rationale_spans: dict[FactorId, str] = Field(default_factory=dict)
    agreement: dict[FactorId, float] | None = None

    @model_validator(mode="after")
    def _status_matches_failure_type(self) -> ExtractionOutcome:
        if self.status == "success" and self.failure_type is not None:
            msg = "a successful outcome must not carry a failure_type"
            raise ValueError(msg)
        if self.status == "failed" and self.failure_type is None:
            msg = "a failed outcome must carry a failure_type"
            raise ValueError(msg)
        return self
