"""`extract_factors`/`extract_factors_self_consistency`: the orchestrator, exercised
against every M5 §12 fake-provider scenario. No test here calls a network."""

from __future__ import annotations

import json

from mindtrace.domain.enums import ExtractionFailureType, ExtractionMode
from mindtrace.domain.ids import FactorId
from mindtrace.llm.errors import ProviderTimeoutError, ProviderUnavailableError
from mindtrace.llm.extraction import extract_factors, extract_factors_self_consistency
from mindtrace.llm.providers.fake import FakeLLMClient
from mindtrace.llm.schema import ExtractionOutcome
from tests.support.llm_fixtures import (
    DEFAULT_CONFIG,
    SCENARIO,
    TAXONOMY,
    duplicate_factor_response,
    extraction_ambiguity_response,
    invalid_numeric_value_response,
    malformed_json_response,
    missing_field_response,
    prompt_injection_response,
    rationale_span_not_in_scenario_response,
    unknown_factor_response,
    unknown_level_response,
    valid_response,
)


def _extract(response: str) -> ExtractionOutcome:
    client = FakeLLMClient(responses=[response])
    return extract_factors(SCENARIO, TAXONOMY, client, config=DEFAULT_CONFIG)


def _extract_sc(client: FakeLLMClient) -> ExtractionOutcome:
    return extract_factors_self_consistency(SCENARIO, TAXONOMY, client, config=DEFAULT_CONFIG)


class TestValidExtraction:
    """1. valid extraction."""

    def test_succeeds_and_covers_the_full_taxonomy(self) -> None:
        outcome = _extract(valid_response())
        assert outcome.status == "success"
        assert outcome.failure_type is None
        assert set(outcome.factors.readings) == set(TAXONOMY.core_ids)
        assert "skill_growth" in outcome.factors.known_ids()
        span = outcome.rationale_spans[FactorId("skill_growth")]
        assert span == "uses the tech stack I want to learn"

    def test_metadata_is_fully_populated(self) -> None:
        outcome = _extract(valid_response())
        assert outcome.metadata.factor_schema_version == TAXONOMY.version
        assert outcome.metadata.provider == "fake"
        assert outcome.metadata.model == "fake-deterministic-v1"
        assert outcome.metadata.mode is ExtractionMode.SINGLE
        assert outcome.metadata.temperature == 0.0


class TestMalformedJson:
    """2. malformed JSON."""

    def test_fails_closed_with_every_factor_unknown(self) -> None:
        outcome = _extract(malformed_json_response())
        assert outcome.status == "failed"
        assert outcome.failure_type is ExtractionFailureType.MALFORMED_OUTPUT
        assert outcome.factors.known_ids() == ()
        assert set(outcome.factors.readings) == set(TAXONOMY.core_ids)


class TestUnknownFactor:
    """3. unknown factor."""

    def test_fails_closed_as_taxonomy_validation(self) -> None:
        outcome = _extract(unknown_factor_response())
        assert outcome.status == "failed"
        assert outcome.failure_type is ExtractionFailureType.TAXONOMY_VALIDATION_FAILED
        assert outcome.factors.known_ids() == ()


class TestUnknownLevel:
    """4. unknown level."""

    def test_fails_closed_as_taxonomy_validation(self) -> None:
        outcome = _extract(unknown_level_response())
        assert outcome.status == "failed"
        assert outcome.failure_type is ExtractionFailureType.TAXONOMY_VALIDATION_FAILED


class TestMissingField:
    """5. missing field."""

    def test_fails_closed_as_malformed_output(self) -> None:
        outcome = _extract(missing_field_response())
        assert outcome.status == "failed"
        assert outcome.failure_type is ExtractionFailureType.MALFORMED_OUTPUT


class TestDuplicateFactor:
    """6. duplicate factor."""

    def test_fails_closed_as_malformed_output(self) -> None:
        outcome = _extract(duplicate_factor_response())
        assert outcome.status == "failed"
        assert outcome.failure_type is ExtractionFailureType.MALFORMED_OUTPUT


class TestInvalidNumericValue:
    """7. invalid numeric value (`known` as an int, not a bool)."""

    def test_fails_closed_as_malformed_output(self) -> None:
        outcome = _extract(invalid_numeric_value_response())
        assert outcome.status == "failed"
        assert outcome.failure_type is ExtractionFailureType.MALFORMED_OUTPUT


class TestPromptInjectionAttempt:
    """8. the provider "obeys" an injection instead of returning the schema."""

    def test_non_json_response_fails_closed_never_producing_a_decision(self) -> None:
        outcome = _extract(prompt_injection_response())
        assert outcome.status == "failed"
        assert outcome.failure_type is ExtractionFailureType.MALFORMED_OUTPUT
        assert outcome.factors.known_ids() == ()


class TestExtractionAmbiguity:
    """9. every factor honestly `known=false` - a valid, non-failure outcome."""

    def test_succeeds_with_zero_known_factors(self) -> None:
        outcome = _extract(extraction_ambiguity_response())
        assert outcome.status == "success"
        assert outcome.factors.known_ids() == ()


class TestProviderFailure:
    """10. provider failure (unreachable, or timed out)."""

    def test_provider_unavailable_fails_closed(self) -> None:
        client = FakeLLMClient(raises=ProviderUnavailableError("no network"))
        outcome = extract_factors(SCENARIO, TAXONOMY, client, config=DEFAULT_CONFIG)
        assert outcome.status == "failed"
        assert outcome.failure_type is ExtractionFailureType.PROVIDER_UNAVAILABLE
        assert outcome.factors.known_ids() == ()

    def test_provider_timeout_fails_closed(self) -> None:
        client = FakeLLMClient(raises=ProviderTimeoutError("deadline exceeded"))
        outcome = extract_factors(SCENARIO, TAXONOMY, client, config=DEFAULT_CONFIG)
        assert outcome.status == "failed"
        assert outcome.failure_type is ExtractionFailureType.PROVIDER_TIMEOUT


class TestRationaleSpanFabrication:
    """Bonus: a well-formed factor whose evidence was invented, not quoted."""

    def test_fails_closed_as_taxonomy_validation(self) -> None:
        outcome = _extract(rationale_span_not_in_scenario_response())
        assert outcome.status == "failed"
        assert outcome.failure_type is ExtractionFailureType.TAXONOMY_VALIDATION_FAILED


class TestFailureDetailIsBounded:
    def test_failure_detail_is_truncated_and_never_none_on_failure(self) -> None:
        long_detail = "x" * 10_000
        client = FakeLLMClient(raises=ProviderUnavailableError(long_detail))
        outcome = extract_factors(SCENARIO, TAXONOMY, client, config=DEFAULT_CONFIG)
        assert outcome.failure_detail is not None
        assert len(outcome.failure_detail) < 250


class TestSelfConsistency:
    def test_two_identical_passes_give_full_agreement(self) -> None:
        response = valid_response()
        client = FakeLLMClient(responses=[response, response])
        outcome = _extract_sc(client)
        assert outcome.metadata.mode is ExtractionMode.SELF_CONSISTENCY
        assert outcome.agreement is not None
        assert all(value == 1.0 for value in outcome.agreement.values())

    def test_client_is_called_exactly_twice(self) -> None:
        response = valid_response()
        client = FakeLLMClient(responses=[response, response])
        _extract_sc(client)
        assert len(client.calls) == 2

    def test_a_failure_on_the_first_pass_short_circuits(self) -> None:
        client = FakeLLMClient(responses=[malformed_json_response()])
        outcome = _extract_sc(client)
        assert outcome.status == "failed"
        assert len(client.calls) == 1

    def test_a_failure_on_the_second_pass_is_returned_as_a_failure(self) -> None:
        client = FakeLLMClient(responses=[valid_response(), malformed_json_response()])
        outcome = _extract_sc(client)
        assert outcome.status == "failed"
        assert len(client.calls) == 2

    def test_disagreement_on_a_second_pass_becoming_unknown_scores_zero(self) -> None:
        first = json.dumps(
            {
                "schema_version": "1",
                "factors": [
                    {
                        "factor_id": "skill_growth",
                        "known": True,
                        "level": "very_high",
                        "rationale_span": "uses the tech stack I want to learn",
                    }
                ],
            }
        )
        second_factors = [{"factor_id": "skill_growth", "known": False}]
        second = json.dumps({"schema_version": "1", "factors": second_factors})
        client = FakeLLMClient(responses=[first, second])
        outcome = _extract_sc(client)
        assert outcome.agreement == {"skill_growth": 0.0}
