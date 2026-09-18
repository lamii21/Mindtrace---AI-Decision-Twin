"""Construction-time invariants of `mindtrace.llm.schema`'s raw contract types."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mindtrace.domain.decision import FactorReading, FactorVector
from mindtrace.domain.enums import ExtractionFailureType, ExtractionMode
from mindtrace.domain.ids import FactorId
from mindtrace.llm.schema import (
    ExtractionMetadata,
    ExtractionOutcome,
    RawExtractedFactor,
    RawExtraction,
)


class TestRawExtractedFactor:
    def test_known_true_requires_a_level(self) -> None:
        with pytest.raises(ValidationError, match="requires a level"):
            RawExtractedFactor(factor_id="skill_growth", known=True, rationale_span="x")

    def test_known_true_requires_a_rationale_span(self) -> None:
        with pytest.raises(ValidationError, match="rationale_span"):
            RawExtractedFactor(factor_id="skill_growth", known=True, level="high")

    def test_known_false_must_not_carry_a_level(self) -> None:
        with pytest.raises(ValidationError, match="must not carry a level"):
            RawExtractedFactor(factor_id="skill_growth", known=False, level="high")

    def test_known_false_must_not_carry_a_rationale_span(self) -> None:
        with pytest.raises(ValidationError, match="must not carry a rationale_span"):
            RawExtractedFactor(factor_id="skill_growth", known=False, rationale_span="x")

    def test_valid_known_factor_is_accepted(self) -> None:
        factor = RawExtractedFactor(
            factor_id="skill_growth", known=True, level="high", rationale_span="x"
        )
        assert factor.level == "high"

    def test_valid_unknown_factor_is_accepted(self) -> None:
        factor = RawExtractedFactor(factor_id="skill_growth", known=False)
        assert factor.level is None

    def test_extra_field_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RawExtractedFactor.model_validate(
                {"factor_id": "skill_growth", "known": False, "confidence": 0.9}
            )

    def test_rationale_span_beyond_max_length_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RawExtractedFactor(
                factor_id="skill_growth", known=True, level="high", rationale_span="x" * 1000
            )


class TestRawExtraction:
    def test_duplicate_factor_ids_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate factor_id"):
            RawExtraction(
                factors=(
                    RawExtractedFactor(factor_id="skill_growth", known=False),
                    RawExtractedFactor(factor_id="skill_growth", known=False),
                )
            )

    def test_valid_extraction_is_accepted(self) -> None:
        extraction = RawExtraction(
            factors=(
                RawExtractedFactor(factor_id="skill_growth", known=False),
                RawExtractedFactor(factor_id="financial_return", known=False),
            )
        )
        assert len(extraction.factors) == 2

    def test_empty_factors_list_is_accepted(self) -> None:
        extraction = RawExtraction(factors=())
        assert extraction.factors == ()

    def test_wrong_schema_version_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RawExtraction.model_validate({"schema_version": "2", "factors": []})


class TestExtractionOutcome:
    def _metadata(self) -> ExtractionMetadata:
        return ExtractionMetadata(
            factor_schema_version=1,
            extraction_schema_version="1",
            prompt_version="extract_factors.v1",
            provider="fake",
            model="fake-v1",
            mode=ExtractionMode.SINGLE,
            temperature=0.0,
        )

    def _empty_factors(self) -> FactorVector:
        return FactorVector.from_items([(FactorId("skill_growth"), FactorReading(known=False))])

    def test_success_with_a_failure_type_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must not carry a failure_type"):
            ExtractionOutcome(
                status="success",
                factors=self._empty_factors(),
                metadata=self._metadata(),
                failure_type=ExtractionFailureType.MALFORMED_OUTPUT,
            )

    def test_failed_without_a_failure_type_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must carry a failure_type"):
            ExtractionOutcome(
                status="failed", factors=self._empty_factors(), metadata=self._metadata()
            )

    def test_valid_success_outcome_is_accepted(self) -> None:
        outcome = ExtractionOutcome(
            status="success", factors=self._empty_factors(), metadata=self._metadata()
        )
        assert outcome.failure_type is None

    def test_valid_failure_outcome_is_accepted(self) -> None:
        outcome = ExtractionOutcome(
            status="failed",
            factors=self._empty_factors(),
            metadata=self._metadata(),
            failure_type=ExtractionFailureType.PROVIDER_UNAVAILABLE,
        )
        assert outcome.failure_type is ExtractionFailureType.PROVIDER_UNAVAILABLE

    def test_is_frozen(self) -> None:
        outcome = ExtractionOutcome(
            status="success", factors=self._empty_factors(), metadata=self._metadata()
        )
        with pytest.raises(ValidationError):
            outcome.status = "failed"
