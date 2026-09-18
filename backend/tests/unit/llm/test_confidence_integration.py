"""M5 §8: `ExtractionOutcome.agreement` plugs directly into `engines.confidence`'s
`ExtractionSignal.self_consistency` - zero adapter code, zero change to the
confidence formula. `mindtrace.llm` never imports `mindtrace.engines.*` in
production code (`.importlinter`'s `llm-is-contained` contract); this test is
the one place that composes them, proving the shapes already match.
"""

from __future__ import annotations

from mindtrace.domain.confidence import ExtractionSignal
from mindtrace.llm.config import ExtractionConfig
from mindtrace.llm.extraction import extract_factors, extract_factors_self_consistency
from mindtrace.llm.providers.fake import FakeLLMClient
from tests.support.llm_fixtures import SCENARIO, TAXONOMY, valid_response


def test_extraction_agreement_builds_a_valid_extraction_signal_with_no_adapter() -> None:
    response = valid_response()
    client = FakeLLMClient(responses=[response, response])
    config = ExtractionConfig(provider="fake", model="fake-v1")
    outcome = extract_factors_self_consistency(SCENARIO, TAXONOMY, client, config=config)

    assert outcome.agreement is not None
    signal = ExtractionSignal.self_consistency(outcome.agreement)

    assert signal.path == "self_consistency"
    assert signal.agreement == outcome.agreement


def test_single_mode_outcome_has_no_agreement_and_is_not_offered_to_extraction_signal() -> None:
    """A `single`-mode outcome has `agreement=None` - a caller must not (and,
    per `ExtractionSignal`'s own validator, cannot) build a `self_consistency`
    signal from it; that is the caller's job to gate on `outcome.metadata.mode`,
    not something either package auto-detects for the other."""
    response = valid_response()
    client = FakeLLMClient(responses=[response])
    config = ExtractionConfig(provider="fake", model="fake-v1")
    outcome = extract_factors(SCENARIO, TAXONOMY, client, config=config)
    assert outcome.agreement is None
