"""`validate_against_taxonomy`: the layer that actually enforces M5 §3/§6."""

from __future__ import annotations

import pytest

from mindtrace.domain.ids import FactorId
from mindtrace.llm.errors import TaxonomyValidationError
from mindtrace.llm.schema import RawExtractedFactor, RawExtraction
from mindtrace.llm.validation import validate_against_taxonomy
from tests.support.llm_fixtures import SCENARIO, TAXONOMY


def _raw(*factors: RawExtractedFactor) -> RawExtraction:
    return RawExtraction(factors=tuple(factors))


class TestValidExtraction:
    def test_covers_every_core_factor_even_when_the_llm_mentioned_only_some(self) -> None:
        raw = _raw(
            RawExtractedFactor(
                factor_id="skill_growth",
                known=True,
                level="very_high",
                rationale_span="tech stack I want to learn",
            )
        )
        factors, rationale_spans = validate_against_taxonomy(raw, TAXONOMY, SCENARIO)
        assert set(factors.readings) == set(TAXONOMY.core_ids)
        assert factors.readings[FactorId("skill_growth")].known is True
        assert factors.readings[FactorId("downside_risk")].known is False
        assert rationale_spans == {FactorId("skill_growth"): "tech stack I want to learn"}

    def test_known_false_factor_carries_no_rationale_span(self) -> None:
        raw = _raw(RawExtractedFactor(factor_id="skill_growth", known=False))
        _, rationale_spans = validate_against_taxonomy(raw, TAXONOMY, SCENARIO)
        assert rationale_spans == {}


class TestUnknownFactor:
    def test_unknown_factor_id_is_rejected(self) -> None:
        raw = _raw(
            RawExtractedFactor(
                factor_id="intelligence", known=True, level="high", rationale_span="pays"
            )
        )
        with pytest.raises(TaxonomyValidationError, match="unknown factor_id"):
            validate_against_taxonomy(raw, TAXONOMY, SCENARIO)

    def test_extended_non_core_factor_is_rejected(self) -> None:
        raw = _raw(
            RawExtractedFactor(factor_id="novelty", known=True, level="high", rationale_span="pays")
        )
        with pytest.raises(TaxonomyValidationError, match="not a core"):
            validate_against_taxonomy(raw, TAXONOMY, SCENARIO)


class TestUnknownLevel:
    def test_unknown_level_is_rejected(self) -> None:
        raw = _raw(
            RawExtractedFactor(
                factor_id="skill_growth",
                known=True,
                level="extremely_high",
                rationale_span="tech stack",
            )
        )
        with pytest.raises(TaxonomyValidationError, match="unknown level"):
            validate_against_taxonomy(raw, TAXONOMY, SCENARIO)


class TestRationaleSpanGrounding:
    def test_rationale_span_not_in_scenario_text_is_rejected(self) -> None:
        raw = _raw(
            RawExtractedFactor(
                factor_id="skill_growth",
                known=True,
                level="high",
                rationale_span="this sentence never appeared anywhere",
            )
        )
        with pytest.raises(TaxonomyValidationError, match="not a literal substring"):
            validate_against_taxonomy(raw, TAXONOMY, SCENARIO)

    def test_rationale_span_that_is_an_exact_substring_is_accepted(self) -> None:
        raw = _raw(
            RawExtractedFactor(
                factor_id="skill_growth",
                known=True,
                level="high",
                rationale_span="pays 1400 EUR/month",
            )
        )
        factors, rationale_spans = validate_against_taxonomy(raw, TAXONOMY, SCENARIO)
        assert factors.readings[FactorId("skill_growth")].known is True
        assert rationale_spans[FactorId("skill_growth")] == "pays 1400 EUR/month"
