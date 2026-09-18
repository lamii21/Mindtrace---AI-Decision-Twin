"""Cross-check a schema-valid `RawExtraction` against the authoritative `FactorTaxonomy`.

This is the layer that actually enforces "unknown factors/levels are
rejected" and "rationale_span must be tied to the scenario text" (M5 §3, §6) -
`schema.py`'s Pydantic models alone cannot check these because they have no
taxonomy or scenario text to check against. Never coerces an invalid value
into a valid one: any violation raises `TaxonomyValidationError`, and
`extraction.py` turns that into a failed `ExtractionOutcome`.
"""

from __future__ import annotations

from mindtrace.domain.decision import FactorReading, FactorVector
from mindtrace.domain.enums import ScaleLevel
from mindtrace.domain.factors import FactorTaxonomy
from mindtrace.domain.ids import FactorId
from mindtrace.llm.errors import TaxonomyValidationError
from mindtrace.llm.schema import RawExtraction


def validate_against_taxonomy(
    raw: RawExtraction, taxonomy: FactorTaxonomy, scenario_text: str
) -> tuple[FactorVector, dict[FactorId, str]]:
    """`(factors, rationale_spans)` - `factors` always covers every core factor.

    Raises:
        TaxonomyValidationError: an id is unknown or non-core, a level is not
            a real `ScaleLevel`, or a `rationale_span` is not a literal
            substring of `scenario_text`.
    """
    items: list[tuple[FactorId, FactorReading]] = []
    rationale_spans: dict[FactorId, str] = {}
    seen: set[FactorId] = set()

    for raw_factor in raw.factors:
        factor_id = _validate_factor_id(raw_factor.factor_id, taxonomy)
        seen.add(factor_id)
        if not raw_factor.known:
            items.append((factor_id, FactorReading(known=False)))
            continue

        assert raw_factor.level is not None  # RawExtractedFactor's own validator guarantees this
        level = _validate_level(raw_factor.level, factor_id)
        assert raw_factor.rationale_span is not None
        _validate_rationale_span(raw_factor.rationale_span, factor_id, scenario_text)

        items.append((factor_id, FactorReading(known=True, level=level)))
        rationale_spans[factor_id] = raw_factor.rationale_span

    for factor_id in taxonomy.core_ids:
        if factor_id not in seen:
            items.append((factor_id, FactorReading(known=False)))

    return FactorVector.from_items(items), rationale_spans


def _validate_factor_id(raw_factor_id: str, taxonomy: FactorTaxonomy) -> FactorId:
    if raw_factor_id not in taxonomy:
        msg = f"unknown factor_id: {raw_factor_id!r}"
        raise TaxonomyValidationError(msg)
    factor_id = FactorId(raw_factor_id)
    if factor_id not in taxonomy.core_ids:
        msg = f"factor_id {raw_factor_id!r} is not a core (v1-aggregated) factor"
        raise TaxonomyValidationError(msg)
    return factor_id


def _validate_level(raw_level: str, factor_id: FactorId) -> ScaleLevel:
    try:
        return ScaleLevel(raw_level)
    except ValueError as exc:
        msg = f"unknown level {raw_level!r} for factor {factor_id!r}"
        raise TaxonomyValidationError(msg) from exc


def _validate_rationale_span(rationale_span: str, factor_id: FactorId, scenario_text: str) -> None:
    if rationale_span not in scenario_text:
        msg = f"rationale_span for {factor_id!r} is not a literal substring of the scenario text"
        raise TaxonomyValidationError(msg)
