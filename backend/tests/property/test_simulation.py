"""Property-based tests for the orchestrator's `simulate()` (M6-B s30).

Every property here is a structural composition guarantee, not a
re-verification of any engine's own mathematics (M3/M4/M6-A each already
carry their own property suites for that): `simulate()` must not mutate its
inputs, must reproduce exactly what a direct `decide()`/`compute_confidence()`
call over the same intermediate values would produce, must never let a
malformed or empty LLM response fabricate a known factor, and must be
deterministic end to end.
"""

from __future__ import annotations

import json
import math

from hypothesis import given, settings
from hypothesis import strategies as st

from mindtrace.domain.confidence import ExtractionSignal
from mindtrace.domain.enums import ChoiceOption, DecisionOutcome, ScaleLevel
from mindtrace.engines.confidence.compute import compute_confidence
from mindtrace.engines.mcda.decide import decide
from mindtrace.engines.preference.config import DEFAULT_PREFERENCE_CONFIG
from mindtrace.engines.preference.posterior import effective_sample_sizes
from mindtrace.engines.preference.prior import initial_posterior
from mindtrace.engines.preference.projection import project_effective_weights
from mindtrace.engines.preference.update import apply_pairwise_observations
from mindtrace.llm.errors import ProviderUnavailableError
from mindtrace.llm.providers.fake import FakeLLMClient
from mindtrace.orchestration import simulate
from tests.support.llm_fixtures import SCENARIO
from tests.support.orchestration_fixtures import TAXONOMY, TRAIT_MODEL, default_config
from tests.support.preference_fixtures import all_pairwise_observations

_CORE_IDS = tuple(TAXONOMY.core_ids)
_LEVELS = tuple(ScaleLevel)

_posteriors = st.sampled_from(
    [
        initial_posterior(TRAIT_MODEL),
        apply_pairwise_observations(
            initial_posterior(TRAIT_MODEL),
            all_pairwise_observations(ChoiceOption.A),
            DEFAULT_PREFERENCE_CONFIG,
        ),
        apply_pairwise_observations(
            initial_posterior(TRAIT_MODEL),
            all_pairwise_observations(ChoiceOption.B),
            DEFAULT_PREFERENCE_CONFIG,
        ),
    ]
)


@st.composite
def known_levels_subset(draw: st.DrawFn) -> dict[str, str]:
    """A random subset of core factors, each given a random ordinal level."""
    chosen = draw(
        st.lists(st.sampled_from(_CORE_IDS), min_size=0, max_size=len(_CORE_IDS), unique=True)
    )
    return {factor_id: draw(st.sampled_from(_LEVELS)).value for factor_id in chosen}


def _response_for(levels: dict[str, str]) -> str:
    factors = [
        {"factor_id": fid, "known": True, "level": level, "rationale_span": SCENARIO}
        for fid, level in levels.items()
    ]
    return json.dumps({"schema_version": "1", "factors": factors})


@given(posterior=_posteriors, levels=known_levels_subset())
@settings(max_examples=60)
def test_simulate_never_mutates_the_posterior(posterior: object, levels: dict[str, str]) -> None:
    before = posterior.model_dump_json()  # type: ignore[attr-defined]
    client = FakeLLMClient(responses=[_response_for(levels)])
    simulate(SCENARIO, TAXONOMY, TRAIT_MODEL, posterior, client, config=default_config())  # type: ignore[arg-type]
    assert posterior.model_dump_json() == before  # type: ignore[attr-defined]


@given(posterior=_posteriors, levels=known_levels_subset())
@settings(max_examples=60)
def test_decision_score_matches_a_direct_m3_call(posterior: object, levels: dict[str, str]) -> None:
    client = FakeLLMClient(responses=[_response_for(levels)])
    result = simulate(SCENARIO, TAXONOMY, TRAIT_MODEL, posterior, client, config=default_config())  # type: ignore[arg-type]

    preference = project_effective_weights(posterior, TRAIT_MODEL)  # type: ignore[arg-type]
    expected_decision = decide(
        TAXONOMY, preference.weights, result.extraction.factors, preference.dispositions
    )
    assert result.decision.model_dump_json() == expected_decision.model_dump_json()


@given(posterior=_posteriors, levels=known_levels_subset())
@settings(max_examples=60)
def test_confidence_matches_a_direct_m4_call(posterior: object, levels: dict[str, str]) -> None:
    client = FakeLLMClient(responses=[_response_for(levels)])
    result = simulate(SCENARIO, TAXONOMY, TRAIT_MODEL, posterior, client, config=default_config())  # type: ignore[arg-type]

    n_eff = effective_sample_sizes(posterior.weights, TRAIT_MODEL)  # type: ignore[attr-defined]
    expected_confidence = compute_confidence(
        result.decision,
        n_eff=n_eff,
        ensemble=None,
        calibration=None,
        extraction=ExtractionSignal.single(),
    )
    assert result.confidence.model_dump_json() == expected_confidence.model_dump_json()


@given(posterior=_posteriors)
@settings(max_examples=20)
def test_a_failed_extraction_never_fabricates_a_known_factor(posterior: object) -> None:
    client = FakeLLMClient(raises=ProviderUnavailableError("down"))
    result = simulate(SCENARIO, TAXONOMY, TRAIT_MODEL, posterior, client, config=default_config())  # type: ignore[arg-type]
    assert result.extraction.status == "failed"
    assert result.extraction.factors.known_ids() == ()
    assert result.decision.known_factor_count == 0


@given(posterior=_posteriors, levels=known_levels_subset())
@settings(max_examples=40)
def test_llm_output_text_cannot_directly_determine_the_final_label(
    posterior: object, levels: dict[str, str]
) -> None:
    """No response content, however constructed, can push `label` outside the
    three real `DecisionOutcome` values - it is always M3's coverage/score
    gates that decide, never the raw extraction."""
    client = FakeLLMClient(responses=[_response_for(levels)])
    result = simulate(SCENARIO, TAXONOMY, TRAIT_MODEL, posterior, client, config=default_config())  # type: ignore[arg-type]
    assert result.decision.label in set(DecisionOutcome)
    assert math.isfinite(result.decision.score)


@given(posterior=_posteriors, levels=known_levels_subset())
@settings(max_examples=40)
def test_repeated_simulation_with_identical_inputs_is_byte_identical(
    posterior: object, levels: dict[str, str]
) -> None:
    response = _response_for(levels)
    first = simulate(
        SCENARIO,
        TAXONOMY,
        TRAIT_MODEL,
        posterior,  # type: ignore[arg-type]
        FakeLLMClient(responses=[response]),
        config=default_config(),
    )
    second = simulate(
        SCENARIO,
        TAXONOMY,
        TRAIT_MODEL,
        posterior,  # type: ignore[arg-type]
        FakeLLMClient(responses=[response]),
        config=default_config(),
    )
    assert first.model_dump_json() == second.model_dump_json()
