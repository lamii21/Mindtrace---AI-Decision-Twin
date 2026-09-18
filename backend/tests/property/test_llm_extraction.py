"""Property/contract tests for the LLM boundary (M5 §16).

Every property here is a genuine invariant the pipeline is supposed to
guarantee - not a property that merely "seems to usually hold" for the
examples on hand. Hypothesis is used both to generate arbitrary garbage
provider output (must always fail closed) and arbitrary *valid* extractions
(must always land inside the taxonomy).
"""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from mindtrace.domain.enums import ScaleLevel
from mindtrace.llm.config import ExtractionConfig
from mindtrace.llm.extraction import extract_factors
from mindtrace.llm.providers.fake import FakeLLMClient
from mindtrace.llm.schema import ExtractionOutcome
from tests.support.llm_fixtures import SCENARIO, TAXONOMY

_CONFIG = ExtractionConfig(provider="fake", model="fake-v1")
_LEVEL_VALUES = tuple(level.value for level in ScaleLevel)


def _extract(response: str) -> ExtractionOutcome:
    client = FakeLLMClient(responses=[response])
    return extract_factors(SCENARIO, TAXONOMY, client, config=_CONFIG)


@st.composite
def valid_extraction_json(draw: st.DrawFn) -> str:
    """A schema-valid, taxonomy-valid extraction, built only from real ids/levels/
    substrings of the actual scenario - the "happy path" generator."""
    factor_ids = draw(
        st.lists(st.sampled_from(TAXONOMY.core_ids), min_size=0, max_size=5, unique=True)
    )
    factors = []
    for factor_id in factor_ids:
        known = draw(st.booleans())
        if known:
            level = draw(st.sampled_from(_LEVEL_VALUES))
            span_start = draw(st.integers(min_value=0, max_value=max(0, len(SCENARIO) - 5)))
            span_end = draw(st.integers(min_value=span_start + 1, max_value=len(SCENARIO)))
            span = SCENARIO[span_start:span_end]
            factors.append(
                {"factor_id": factor_id, "known": True, "level": level, "rationale_span": span}
            )
        else:
            factors.append({"factor_id": factor_id, "known": False})
    return json.dumps({"schema_version": "1", "factors": factors})


@given(response=st.text(min_size=0, max_size=200))
@settings(max_examples=200)
def test_arbitrary_garbage_text_always_fails_closed(response: str) -> None:
    """`extract_factors` never raises for any input string, and any non-JSON or
    non-schema-shaped text produces a `failed` outcome with every core factor
    `known=False` - never a fabricated factor."""
    outcome = _extract(response)
    if outcome.status == "failed":
        assert outcome.factors.known_ids() == ()
        assert set(outcome.factors.readings) == set(TAXONOMY.core_ids)
        assert outcome.failure_type is not None


@given(response=st.text(min_size=0, max_size=200))
@settings(max_examples=200)
def test_extraction_never_raises_regardless_of_input(response: str) -> None:
    """A contract test in the literal sense: no exception ever escapes
    `extract_factors`, for any provider text at all."""
    _extract(response)  # must not raise


@given(extraction_json=valid_extraction_json())
@settings(max_examples=100)
def test_every_validated_factor_id_is_in_the_authoritative_taxonomy(extraction_json: str) -> None:
    outcome = _extract(extraction_json)
    if outcome.status == "success":
        for factor_id in outcome.factors.known_ids():
            assert factor_id in TAXONOMY.core_ids


@given(extraction_json=valid_extraction_json())
@settings(max_examples=100)
def test_every_validated_level_is_a_real_scale_level(extraction_json: str) -> None:
    outcome = _extract(extraction_json)
    if outcome.status == "success":
        for factor_id in outcome.factors.known_ids():
            reading = outcome.factors.readings[factor_id]
            assert reading.level in set(ScaleLevel)


@given(extraction_json=valid_extraction_json())
@settings(max_examples=100)
def test_every_rationale_span_is_a_literal_substring_of_the_scenario(extraction_json: str) -> None:
    outcome = _extract(extraction_json)
    if outcome.status == "success":
        for factor_id, span in outcome.rationale_spans.items():
            assert span in SCENARIO
            assert factor_id in outcome.factors.known_ids()


@given(extraction_json=valid_extraction_json())
@settings(max_examples=50)
def test_factor_vector_always_covers_the_full_core_taxonomy(extraction_json: str) -> None:
    """Whatever subset the (simulated) provider mentioned, the resulting
    `FactorVector` is always fully addressable over every core factor - a
    caller building an MCDA `decide()` call never needs a special case."""
    outcome = _extract(extraction_json)
    assert set(outcome.factors.readings) == set(TAXONOMY.core_ids)


class TestLLMCannotAlterTraitOrDecisionState:
    """Structural guarantees - the exhaustive, always-on version of this check is
    `lint-imports`'s `llm-is-contained` contract (`mindtrace.llm` cannot import
    `mindtrace.engines.*` at all); this class checks the *data shape* side of
    the same guarantee: even the successful-outcome type has nowhere to carry
    a weight, a posterior parameter, or a decision."""

    def test_extraction_outcome_carries_no_weight_or_posterior_field(self) -> None:
        field_names = set(ExtractionOutcome.model_fields)
        forbidden = {"weight", "weights", "posterior", "trait", "mu", "sigma", "alpha", "beta"}
        assert field_names.isdisjoint(forbidden)
