"""`simulate()`: the full M6-B test matrix (A-O)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mindtrace.domain.enums import DecisionOutcome, ExtractionMode, UncertainReason
from mindtrace.domain.factors import load_factor_taxonomy
from mindtrace.domain.ids import FactorId
from mindtrace.domain.traits import load_trait_model
from mindtrace.engines.preference.errors import PreferenceValidationError
from mindtrace.llm.errors import ProviderUnavailableError
from mindtrace.llm.providers.fake import FakeLLMClient
from mindtrace.orchestration import SIMULATION_VERSION, SimulationError, simulate
from tests.support.llm_fixtures import (
    malformed_json_response,
    prompt_injection_response,
    rationale_span_not_in_scenario_response,
    valid_response,
)
from tests.support.orchestration_fixtures import (
    SCENARIO,
    TAXONOMY,
    TRAIT_MODEL,
    cold_start_posterior,
    default_config,
    disagreeing_self_consistency_responses,
    fully_known_response,
    near_tie_response,
    self_consistency_config,
    sparse_response,
    strong_evidence_posterior,
)


def _client(*responses: str) -> FakeLLMClient:
    return FakeLLMClient(responses=list(responses))


class TestCompleteSuccessfulSimulation:
    """A. a fully wired call returns one auditable `SimulationResult`."""

    def test_all_four_sub_results_are_present_and_self_consistent(self) -> None:
        client = _client(valid_response())
        result = simulate(
            SCENARIO, TAXONOMY, TRAIT_MODEL, cold_start_posterior(), client, config=default_config()
        )
        assert result.simulation_version == SIMULATION_VERSION
        assert result.extraction.status == "success"
        assert result.preference.trait_schema_version == TRAIT_MODEL.version
        assert result.decision.score is not None
        assert 0.0 <= result.confidence.value <= 1.0
        assert len(client.calls) == 1


class TestColdStart:
    """B. a zero-evidence posterior still produces a complete, valid result."""

    def test_cold_start_posterior_runs_to_completion(self) -> None:
        client = _client(valid_response())
        result = simulate(
            SCENARIO, TAXONOMY, TRAIT_MODEL, cold_start_posterior(), client, config=default_config()
        )
        assert result.preference.total_weight_evidence_count == 0
        assert result.decision.label in set(DecisionOutcome)


class TestStrongPreferenceEvidence:
    """C. real posterior evidence changes the projected weight and the resulting score."""

    def test_evidence_favouring_skill_growth_raises_its_weight_and_the_score(self) -> None:
        cold_client = _client(valid_response())
        cold = simulate(
            SCENARIO,
            TAXONOMY,
            TRAIT_MODEL,
            cold_start_posterior(),
            cold_client,
            config=default_config(),
        )
        strong_client = _client(valid_response())
        strong = simulate(
            SCENARIO,
            TAXONOMY,
            TRAIT_MODEL,
            strong_evidence_posterior(),
            strong_client,
            config=default_config(),
        )
        assert (
            strong.preference.weights.weights[FactorId("skill_growth")]
            > cold.preference.weights.weights[FactorId("skill_growth")]
        )
        assert strong.decision.score > cold.decision.score


class TestExtractionFailure:
    """D. a provider failure flows through M5's own all-unknown fallback - no second one."""

    def test_provider_unavailable_yields_failed_extraction_and_uncertain_decision(self) -> None:
        client = FakeLLMClient(raises=ProviderUnavailableError("no network"))
        result = simulate(
            SCENARIO, TAXONOMY, TRAIT_MODEL, cold_start_posterior(), client, config=default_config()
        )
        assert result.extraction.status == "failed"
        assert result.extraction.factors.known_ids() == ()
        assert result.decision.label is DecisionOutcome.UNCERTAIN
        assert result.decision.uncertain_reason is UncertainReason.INSUFFICIENT_COVERAGE
        assert result.confidence.value == 0.0


class TestInvalidExtraction:
    """E. a schema-valid but taxonomy-invalid response (fabricated rationale) fails closed."""

    def test_fabricated_rationale_span_fails_the_whole_extraction(self) -> None:
        client = _client(rationale_span_not_in_scenario_response())
        result = simulate(
            SCENARIO, TAXONOMY, TRAIT_MODEL, cold_start_posterior(), client, config=default_config()
        )
        assert result.extraction.status == "failed"
        assert result.extraction.failure_type == "taxonomy_validation_failed"


class TestPromptInjection:
    """F. a non-JSON, instruction-shaped provider response can never dictate the label."""

    def test_injected_instruction_text_never_reaches_the_decision(self) -> None:
        client = _client(prompt_injection_response())
        result = simulate(
            SCENARIO, TAXONOMY, TRAIT_MODEL, cold_start_posterior(), client, config=default_config()
        )
        assert result.extraction.status == "failed"
        assert result.decision.label is not DecisionOutcome.ACCEPT


class TestSelfConsistencyDisagreement:
    """G. two disagreeing passes surface as a real agreement<1.0 signal into confidence."""

    def test_disagreement_lowers_extraction_entropy_confidence_input(self) -> None:
        first, second = disagreeing_self_consistency_responses()
        client = _client(first, second)
        result = simulate(
            SCENARIO,
            TAXONOMY,
            TRAIT_MODEL,
            cold_start_posterior(),
            client,
            config=self_consistency_config(),
        )
        assert result.extraction.metadata.mode is ExtractionMode.SELF_CONSISTENCY
        assert result.extraction.agreement == {"skill_growth": 0.0}
        assert result.confidence.inputs.extraction_entropy == pytest.approx(1.0)
        assert len(client.calls) == 2

    def test_malformed_second_pass_propagates_as_a_failed_outcome(self) -> None:
        client = _client(valid_response(), malformed_json_response())
        result = simulate(
            SCENARIO,
            TAXONOMY,
            TRAIT_MODEL,
            cold_start_posterior(),
            client,
            config=self_consistency_config(),
        )
        assert result.extraction.status == "failed"


class TestFullyKnownFactors:
    """H. every core factor known -> full coverage, no coverage-gate UNCERTAIN."""

    def test_full_coverage_is_reported(self) -> None:
        client = _client(fully_known_response())
        result = simulate(
            SCENARIO, TAXONOMY, TRAIT_MODEL, cold_start_posterior(), client, config=default_config()
        )
        assert result.decision.coverage == pytest.approx(1.0)
        assert result.decision.known_factor_count == len(TAXONOMY.core_ids)
        assert result.decision.uncertain_reason is not UncertainReason.INSUFFICIENT_COVERAGE


class TestSparseFactors:
    """I. very few known factors trips M3's coverage gate."""

    def test_two_of_sixteen_known_factors_is_insufficient_coverage(self) -> None:
        client = _client(sparse_response())
        result = simulate(
            SCENARIO, TAXONOMY, TRAIT_MODEL, cold_start_posterior(), client, config=default_config()
        )
        assert result.decision.known_factor_count == 2
        assert result.decision.label is DecisionOutcome.UNCERTAIN
        assert result.decision.uncertain_reason is UncertainReason.INSUFFICIENT_COVERAGE


class TestNearTieDecision:
    """J. full coverage with conflicting evidence -> a genuine score-band UNCERTAIN."""

    def test_alternating_high_low_produces_a_near_zero_score(self) -> None:
        client = _client(near_tie_response())
        result = simulate(
            SCENARIO, TAXONOMY, TRAIT_MODEL, cold_start_posterior(), client, config=default_config()
        )
        assert result.decision.coverage == pytest.approx(1.0)
        assert abs(result.decision.score) < 0.1
        assert result.decision.label is DecisionOutcome.UNCERTAIN
        assert result.decision.uncertain_reason is UncertainReason.SCORE_IN_BAND


class TestPreferencePosteriorImmutability:
    """K. `simulate()` never mutates the caller's posterior object."""

    def test_posterior_is_byte_identical_before_and_after(self) -> None:
        posterior = strong_evidence_posterior()
        before = posterior.model_dump_json()
        client = _client(valid_response())
        simulate(SCENARIO, TAXONOMY, TRAIT_MODEL, posterior, client, config=default_config())
        assert posterior.model_dump_json() == before


class TestTraitModelImmutability:
    """L. `simulate()` never mutates the caller's trait model object."""

    def test_trait_model_is_byte_identical_before_and_after(self) -> None:
        trait_model = TRAIT_MODEL
        before = trait_model.model_dump_json()
        client = _client(valid_response())
        simulate(
            SCENARIO, TAXONOMY, trait_model, cold_start_posterior(), client, config=default_config()
        )
        assert trait_model.model_dump_json() == before


class TestDeterminism:
    """M. identical inputs (incl. a fresh, identically-scripted fake client) match exactly."""

    def test_two_runs_with_identical_inputs_produce_byte_identical_results(self) -> None:
        posterior = cold_start_posterior()
        first = simulate(
            SCENARIO,
            TAXONOMY,
            TRAIT_MODEL,
            posterior,
            _client(valid_response()),
            config=default_config(),
        )
        second = simulate(
            SCENARIO,
            TAXONOMY,
            TRAIT_MODEL,
            posterior,
            _client(valid_response()),
            config=default_config(),
        )
        assert first.model_dump_json() == second.model_dump_json()


class TestProvenancePropagation:
    """N. every sub-engine's own version/provenance fields survive composition unchanged."""

    def test_versions_match_each_owning_engine(self) -> None:
        config = default_config()
        client = _client(valid_response())
        result = simulate(
            SCENARIO, TAXONOMY, TRAIT_MODEL, cold_start_posterior(), client, config=config
        )
        assert result.extraction.metadata.provider == config.extraction_config.provider
        assert result.extraction.metadata.model == config.extraction_config.model
        assert result.extraction.metadata.factor_schema_version == TAXONOMY.version
        assert result.preference.trait_schema_version == TRAIT_MODEL.version
        assert result.preference.projection_version == config.projection_version
        assert result.decision.engine_version
        assert result.confidence.confidence_engine_version

    def test_scenario_text_is_never_retained_only_its_hash(self) -> None:
        client = _client(valid_response())
        result = simulate(
            SCENARIO, TAXONOMY, TRAIT_MODEL, cold_start_posterior(), client, config=default_config()
        )
        dumped = result.model_dump_json()
        assert SCENARIO not in dumped
        assert result.scenario_content_hash != SCENARIO


class TestNoHiddenDefaults:
    """O. every engine sub-config actually used is the one named in `SimulationConfig`, not
    some engine's own silently-substituted default."""

    def test_custom_projection_version_is_honoured_end_to_end(self) -> None:
        config = default_config()
        custom = config.model_copy(update={"projection_version": "2-test-orchestration"})
        client = _client(valid_response())
        result = simulate(
            SCENARIO, TAXONOMY, TRAIT_MODEL, cold_start_posterior(), client, config=custom
        )
        assert result.preference.projection_version == "2-test-orchestration"

    def test_extraction_config_has_no_default_provider_or_model(self) -> None:
        with pytest.raises(ValidationError):
            default_config().extraction_config.__class__()  # type: ignore[call-arg]


class TestSchemaCompatibilityCrossCheck:
    """The one genuine composition-level check: taxonomy vs trait-model schema version."""

    def test_mismatched_taxonomy_and_trait_model_versions_raise_simulation_error(self) -> None:
        mismatched_taxonomy = load_factor_taxonomy().model_copy(update={"version": 999})
        client = _client(valid_response())
        with pytest.raises(SimulationError, match="factor_schema_version"):
            simulate(
                SCENARIO,
                mismatched_taxonomy,
                TRAIT_MODEL,
                cold_start_posterior(),
                client,
                config=default_config(),
            )


class TestEngineErrorsPropagateUnwrapped:
    """Engine-level failures are not re-wrapped into `SimulationError`."""

    def test_incompatible_posterior_raises_preference_validation_error_not_simulation_error(
        self,
    ) -> None:
        other_taxonomy = load_factor_taxonomy()
        other_trait_model = load_trait_model(taxonomy=other_taxonomy)
        bad_posterior = cold_start_posterior().model_copy(update={"trait_schema_version": 999})
        client = _client(valid_response())
        with pytest.raises(PreferenceValidationError):
            simulate(
                SCENARIO,
                other_taxonomy,
                other_trait_model,
                bad_posterior,
                client,
                config=default_config(),
            )
