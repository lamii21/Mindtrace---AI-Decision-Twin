"""The extraction boundary's single entry point: `scenario -> ExtractionOutcome`.

Every failure mode - provider unreachable, provider timed out, malformed
JSON, schema-invalid JSON, taxonomy-invalid content - is caught here and
turned into a failed `ExtractionOutcome` carrying every core factor as
`known=False`. Nothing above this function ever sees a raw provider
exception or a partially-trusted factor.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from mindtrace.domain.decision import FactorReading, FactorVector
from mindtrace.domain.enums import ExtractionFailureType, ExtractionMode
from mindtrace.domain.factors import FactorTaxonomy
from mindtrace.domain.ids import FactorId
from mindtrace.llm.client import LLMClient
from mindtrace.llm.config import ExtractionConfig
from mindtrace.llm.errors import (
    ProviderTimeoutError,
    ProviderUnavailableError,
    TaxonomyValidationError,
)
from mindtrace.llm.prompts import build_system_prompt, build_user_content
from mindtrace.llm.schema import ExtractionMetadata, ExtractionOutcome, RawExtraction
from mindtrace.llm.validation import validate_against_taxonomy

_MAX_FAILURE_DETAIL_LENGTH = 200


def extract_factors(
    scenario_text: str,
    taxonomy: FactorTaxonomy,
    client: LLMClient,
    *,
    config: ExtractionConfig,
) -> ExtractionOutcome:
    """Run one extraction pass.

    Always returns a valid `ExtractionOutcome` - never raises, never leaks a
    provider exception.
    """
    metadata = _metadata(taxonomy, config, mode=ExtractionMode.SINGLE)
    system_prompt = build_system_prompt(taxonomy)
    user_content = build_user_content(scenario_text)

    try:
        raw_text = client.generate(system_prompt=system_prompt, user_content=user_content)
    except ProviderUnavailableError as exc:
        return _failure(taxonomy, metadata, ExtractionFailureType.PROVIDER_UNAVAILABLE, str(exc))
    except ProviderTimeoutError as exc:
        return _failure(taxonomy, metadata, ExtractionFailureType.PROVIDER_TIMEOUT, str(exc))

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return _failure(taxonomy, metadata, ExtractionFailureType.MALFORMED_OUTPUT, str(exc))

    try:
        raw_extraction = RawExtraction.model_validate(parsed)
    except ValidationError as exc:
        return _failure(taxonomy, metadata, ExtractionFailureType.MALFORMED_OUTPUT, str(exc))

    try:
        factors, rationale_spans = validate_against_taxonomy(
            raw_extraction, taxonomy, scenario_text
        )
    except TaxonomyValidationError as exc:
        failure_type = ExtractionFailureType.TAXONOMY_VALIDATION_FAILED
        return _failure(taxonomy, metadata, failure_type, str(exc))

    return ExtractionOutcome(
        status="success", factors=factors, metadata=metadata, rationale_spans=rationale_spans
    )


def extract_factors_self_consistency(
    scenario_text: str,
    taxonomy: FactorTaxonomy,
    client: LLMClient,
    *,
    config: ExtractionConfig,
) -> ExtractionOutcome:
    """Two independent passes, compared into a per-factor `agreement` map.

    Over the first pass's known factors (spec/06 §4.4): `1.0` same level,
    `0.5` one ordinal step apart, `0.0` otherwise - including "the second
    pass called it unknown", a real instability, not something to quietly
    exclude. If either pass fails, that failure is returned as-is (no
    partial-agreement result is ever produced from a half-failed pair).
    """
    first = extract_factors(scenario_text, taxonomy, client, config=config)
    if first.status == "failed":
        return first
    second = extract_factors(scenario_text, taxonomy, client, config=config)
    if second.status == "failed":
        return second

    agreement: dict[FactorId, float] = {}
    for factor_id in first.factors.known_ids():
        first_level = first.factors.readings[factor_id].level
        second_reading = second.factors.readings[factor_id]
        assert first_level is not None  # known_ids() guarantees a level is present
        if not second_reading.known:
            agreement[factor_id] = 0.0
            continue
        assert second_reading.level is not None
        rank_diff = abs(first_level.rank - second_reading.level.rank)
        agreement[factor_id] = 1.0 if rank_diff == 0 else (0.5 if rank_diff == 1 else 0.0)

    metadata = _metadata(taxonomy, config, mode=ExtractionMode.SELF_CONSISTENCY)
    return first.model_copy(update={"metadata": metadata, "agreement": agreement})


def _metadata(
    taxonomy: FactorTaxonomy, config: ExtractionConfig, *, mode: ExtractionMode
) -> ExtractionMetadata:
    return ExtractionMetadata(
        factor_schema_version=taxonomy.version,
        extraction_schema_version=config.extraction_schema_version,
        prompt_version=config.prompt_version,
        provider=config.provider,
        model=config.model,
        mode=mode,
        temperature=config.temperature,
    )


def _failure(
    taxonomy: FactorTaxonomy,
    metadata: ExtractionMetadata,
    failure_type: ExtractionFailureType,
    detail: str,
) -> ExtractionOutcome:
    all_unknown = FactorVector.from_items(
        [(factor_id, FactorReading(known=False)) for factor_id in taxonomy.core_ids]
    )
    return ExtractionOutcome(
        status="failed",
        factors=all_unknown,
        metadata=metadata,
        failure_type=failure_type,
        failure_detail=_bounded_detail(detail),
    )


def _bounded_detail(detail: str) -> str:
    """Truncate a failure message before it is stored/logged.

    A parser error can echo a fragment of the provider's raw output, which
    ultimately derives from the (possibly sensitive) scenario text - bounding
    the length limits, without eliminating, that exposure (M5 §20).
    """
    if len(detail) <= _MAX_FAILURE_DETAIL_LENGTH:
        return detail
    return detail[:_MAX_FAILURE_DETAIL_LENGTH] + "..."
