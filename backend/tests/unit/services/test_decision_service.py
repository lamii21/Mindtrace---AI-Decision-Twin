"""Unit tests for ``services/decision_service.py``'s two private, pure helpers (M10 fix).

Both functions are tested in isolation, without a database or an HTTP
client - ``_compose_final_label`` is a plain 3-gate dispatch over
already-computed domain objects, and ``_extraction_signal_for`` is a ~5-line
lookup deliberately duplicated from ``orchestration.simulation``'s own
private helper of the same shape (see that function's docstring). Neither
needs persistence or the LLM boundary to be exercised directly.
"""

from __future__ import annotations

from mindtrace.domain.confidence import ExtractionSignal
from mindtrace.domain.enums import DecisionOutcome, ExtractionMode, UncertainReason
from mindtrace.domain.simulation import TwinConfigResult
from mindtrace.engines.confidence.compute import compute_confidence
from mindtrace.engines.confidence.config import DEFAULT_CONFIDENCE_CONFIG
from mindtrace.engines.debate.synthesis import synthesize
from mindtrace.llm.config import ExtractionConfig
from mindtrace.llm.errors import ProviderUnavailableError
from mindtrace.llm.extraction import extract_factors, extract_factors_self_consistency
from mindtrace.llm.providers.fake import FakeLLMClient
from mindtrace.orchestration.simulation import _extraction_signal_for as _orchestration_signal_for
from mindtrace.services.decision_service import _compose_final_label, _extraction_signal_for
from tests.support.confidence_fixtures import DECISION_EXAMPLE_1
from tests.support.orchestration_fixtures import SCENARIO, TAXONOMY, fully_known_response
from tests.support.twin_fixtures import twin_result_with

_BASE_TWIN_ID = "base"
_EXTRACTION_CONFIG = ExtractionConfig(provider="fake", model="fake-parity-test")
# Gates 1/2 (the two this file targets) both return before `_compose_final_label` ever
# looks at `confidence` - its exact value is irrelevant to those two tests. `_HIGH_
# CONFIDENCE` exists only for the third, "nothing gated" sanity test, where gate 3 (M4's
# own, unmodified confidence gate) must demonstrably *not* fire either - `compute_
# confidence(DECISION_EXAMPLE_1)`'s own bare-default value (0.3) sits below `c_min`
# (0.35) and would otherwise make that test fail for an unrelated reason.
_DEFAULT_CONFIDENCE = compute_confidence(DECISION_EXAMPLE_1)
_HIGH_CONFIDENCE = compute_confidence(
    DECISION_EXAMPLE_1,
    n_eff={c.factor_id: 50.0 for c in DECISION_EXAMPLE_1.contributions},
    extraction=ExtractionSignal.single(),
)


def _decisive_decision(label: DecisionOutcome) -> TwinConfigResult:
    """A ``base`` twin result whose own M3 label is decisive - never ``UNCERTAIN``."""
    assert label is not DecisionOutcome.UNCERTAIN
    return twin_result_with(twin=_BASE_TWIN_ID, contributions={"a": 1.0}, label=label)


class TestComposeFinalLabelEnsembleDisagreementGate:
    """F1: the ``_compose_final_label`` branch returning
    ``(DecisionOutcome.UNCERTAIN, UncertainReason.ENSEMBLE_DISAGREEMENT)`` - unexercised by
    the full suite before this fix (confirmed via a fresh coverage run: line never hit)."""

    def test_fires_when_the_base_twin_is_decisive_but_the_synthesis_vote_is_uncertain(
        self,
    ) -> None:
        """Base twin alone says ACCEPT (gate 1 does not intercept); every other twin votes
        UNCERTAIN, so the weight-of-evidence vote (base counts double, every other twin
        counts once - ``BASE_TWIN_VOTE_WEIGHT``) genuinely lands on UNCERTAIN: ACCEPT=2
        (base only) vs UNCERTAIN=4 (the four named twins) - UNCERTAIN wins outright, not a
        tie. This is a real ``synthesize()`` output, not a hand-built ``SynthesisResult``."""
        base = _decisive_decision(DecisionOutcome.ACCEPT)
        others = [
            twin_result_with(twin=name, contributions={"a": 0.0}, label=DecisionOutcome.UNCERTAIN)
            for name in ("career", "safe", "dream", "future")
        ]
        synthesis = synthesize([base, *others], base_twin_id=_BASE_TWIN_ID)
        assert synthesis.recommended_label is DecisionOutcome.UNCERTAIN  # precondition

        label, reason = _compose_final_label(
            base.decision, synthesis, _DEFAULT_CONFIDENCE, DEFAULT_CONFIDENCE_CONFIG
        )

        assert label is DecisionOutcome.UNCERTAIN
        assert reason is UncertainReason.ENSEMBLE_DISAGREEMENT

    def test_the_base_twins_own_gate_takes_precedence_over_the_ensemble_gate(self) -> None:
        """Gate 1 (M3's own score-band gate) wins even when the synthesis vote also says
        UNCERTAIN - the base twin's own reason must survive, never silently replaced by
        ``ENSEMBLE_DISAGREEMENT`` (``_compose_final_label``'s own documented gate order)."""
        base = twin_result_with(
            twin=_BASE_TWIN_ID,
            contributions={"a": 1.0},
            label=DecisionOutcome.UNCERTAIN,
        )
        base_decision = base.decision.model_copy(
            update={"uncertain_reason": UncertainReason.SCORE_IN_BAND}
        )
        others = [
            twin_result_with(twin=name, contributions={"a": 0.0}, label=DecisionOutcome.UNCERTAIN)
            for name in ("career", "safe", "dream", "future")
        ]
        synthesis = synthesize([base, *others], base_twin_id=_BASE_TWIN_ID)
        assert synthesis.recommended_label is DecisionOutcome.UNCERTAIN  # precondition

        label, reason = _compose_final_label(
            base_decision, synthesis, _DEFAULT_CONFIDENCE, DEFAULT_CONFIDENCE_CONFIG
        )

        assert label is DecisionOutcome.UNCERTAIN
        assert reason is UncertainReason.SCORE_IN_BAND  # not ENSEMBLE_DISAGREEMENT

    def test_a_unanimous_decisive_vote_never_triggers_the_ensemble_gate(self) -> None:
        """Sanity check in the opposite direction: when every twin agrees with the decisive
        base twin, the ensemble gate must not fire and the vote's own label passes through."""
        base = _decisive_decision(DecisionOutcome.ACCEPT)
        others = [
            twin_result_with(twin=name, contributions={"a": 1.0}, label=DecisionOutcome.ACCEPT)
            for name in ("career", "safe", "dream", "future")
        ]
        synthesis = synthesize([base, *others], base_twin_id=_BASE_TWIN_ID)
        assert synthesis.recommended_label is DecisionOutcome.ACCEPT  # precondition

        label, reason = _compose_final_label(
            base.decision, synthesis, _HIGH_CONFIDENCE, DEFAULT_CONFIDENCE_CONFIG
        )

        assert label is DecisionOutcome.ACCEPT
        assert reason is None  # neither gate 2 (ensemble) nor gate 3 (confidence) fired


class TestExtractionSignalForParityWithOrchestration:
    """F2 (root-cause fix): ``decision_service._extraction_signal_for`` is a deliberate
    duplicate of ``orchestration.simulation._extraction_signal_for`` (same ~5-line
    dispatch) so that M10's real-ensemble confidence recompute doesn't have to call back
    into ``orchestration``. This test is the parity check that docstring claims exists -
    before this fix, no such test existed anywhere in the repository."""

    def test_failed_extraction_maps_to_none_in_both_copies(self) -> None:
        client = FakeLLMClient(raises=ProviderUnavailableError("simulated outage"))
        outcome = extract_factors(SCENARIO, TAXONOMY, client, config=_EXTRACTION_CONFIG)
        assert outcome.status == "failed"  # precondition

        assert _extraction_signal_for(outcome) is None
        assert _orchestration_signal_for(outcome) is None

    def test_single_pass_extraction_maps_identically_in_both_copies(self) -> None:
        client = FakeLLMClient(responses=[fully_known_response()])
        outcome = extract_factors(SCENARIO, TAXONOMY, client, config=_EXTRACTION_CONFIG)
        assert outcome.status == "success"  # precondition
        assert outcome.metadata.mode is ExtractionMode.SINGLE  # precondition

        service_signal = _extraction_signal_for(outcome)
        orchestration_signal = _orchestration_signal_for(outcome)
        assert service_signal == orchestration_signal == ExtractionSignal.single()

    def test_self_consistency_extraction_maps_identically_in_both_copies(self) -> None:
        client = FakeLLMClient(responses=[fully_known_response(), fully_known_response()])
        outcome = extract_factors_self_consistency(
            SCENARIO, TAXONOMY, client, config=_EXTRACTION_CONFIG
        )
        assert outcome.status == "success"  # precondition
        assert outcome.metadata.mode is ExtractionMode.SELF_CONSISTENCY  # precondition
        assert outcome.agreement is not None  # precondition

        service_signal = _extraction_signal_for(outcome)
        orchestration_signal = _orchestration_signal_for(outcome)
        assert service_signal == orchestration_signal
        assert service_signal == ExtractionSignal.self_consistency(outcome.agreement)
