"""Typed LLM boundary failures (ADR-003, M5 §19).

Every failure mode a caller needs to distinguish is a real, catchable type -
never a raw provider exception. ``extraction.py`` catches every one of these
internally and turns it into an :class:`~mindtrace.llm.schema.ExtractionOutcome`
with a matching :class:`~mindtrace.domain.enums.ExtractionFailureType`; nothing
here is ever raised past that boundary to a caller.
"""

from __future__ import annotations

from mindtrace.domain.errors import DomainError


class LLMError(DomainError):
    """Base class for every LLM-boundary failure."""


class ProviderUnavailableError(LLMError):
    """The provider could not be reached at all (no network, no credentials, ...)."""


class ProviderTimeoutError(LLMError):
    """The provider was reached but did not respond in time."""


class MalformedOutputError(LLMError):
    """The provider's raw output is not valid JSON, or not the extraction schema's shape."""


class TaxonomyValidationError(LLMError):
    """A schema-valid output references content the taxonomy/scenario reject.

    A factor id, level, or `rationale_span` the authoritative
    `FactorTaxonomy`/scenario text does not support.
    """
