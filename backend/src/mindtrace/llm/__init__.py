"""The LLM boundary (ADR-003): the only package permitted to reach an LLM provider.

The LLM is an untrusted structured extractor, nothing else. This package
turns a scenario's free text into a validated `mindtrace.domain.decision.
FactorVector` (M3's own type) or an explicit, typed failure - it never
computes a score, a confidence value, a weight, or a decision, and it never
imports `mindtrace.engines.*` (`.importlinter`'s `llm-is-contained`
contract). See `extraction.py`'s module docstring for the full pipeline.
"""

from __future__ import annotations

from mindtrace.llm.client import LLMClient
from mindtrace.llm.config import EXTRACTION_SCHEMA_VERSION, ExtractionConfig
from mindtrace.llm.errors import (
    LLMError,
    MalformedOutputError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    TaxonomyValidationError,
)
from mindtrace.llm.extraction import extract_factors, extract_factors_self_consistency
from mindtrace.llm.schema import (
    ExtractionMetadata,
    ExtractionOutcome,
    RawExtractedFactor,
    RawExtraction,
)

__all__ = [
    "EXTRACTION_SCHEMA_VERSION",
    "ExtractionConfig",
    "ExtractionMetadata",
    "ExtractionOutcome",
    "LLMClient",
    "LLMError",
    "MalformedOutputError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "RawExtractedFactor",
    "RawExtraction",
    "TaxonomyValidationError",
    "extract_factors",
    "extract_factors_self_consistency",
]
