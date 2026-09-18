"""Versioned, inspectable extraction configuration (M5 §10-11).

`provider`/`model` have no default: a caller must always say which client
they are actually using, so `ExtractionMetadata` never has to guess. Every
other field pins a specific, reproducible-enough choice - `temperature=0.0`
per ADR-003 rule 5 - rather than leaving it to a provider's own default.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from mindtrace.llm.prompts import PROMPT_VERSION

_FrozenModel = ConfigDict(frozen=True, extra="forbid")

EXTRACTION_SCHEMA_VERSION = "1"
_MAX_TEMPERATURE = 2.0


class ExtractionConfig(BaseModel):
    """One named, versioned set of extraction constants."""

    model_config = _FrozenModel

    extraction_schema_version: str = EXTRACTION_SCHEMA_VERSION
    prompt_version: str = PROMPT_VERSION
    provider: str
    model: str
    temperature: float = 0.0

    @model_validator(mode="after")
    def _validate(self) -> ExtractionConfig:
        if not self.extraction_schema_version.strip():
            msg = "extraction_schema_version must be non-empty"
            raise ValueError(msg)
        if not self.prompt_version.strip():
            msg = "prompt_version must be non-empty"
            raise ValueError(msg)
        if not self.provider.strip():
            msg = "provider must be non-empty"
            raise ValueError(msg)
        if not self.model.strip():
            msg = "model must be non-empty"
            raise ValueError(msg)
        if not 0.0 <= self.temperature <= _MAX_TEMPERATURE:
            msg = f"temperature must be in [0, {_MAX_TEMPERATURE}]"
            raise ValueError(msg)
        return self
