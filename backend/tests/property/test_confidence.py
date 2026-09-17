"""Property-based tests for the confidence engine (M4 s18).

Every property here is one the mathematics in `docs/spec/06-confidence-model.md`
actually guarantees, or one the M4 prompt's absolute invariant demands. Where
a property only holds under an extra condition, the test encodes that
condition explicitly rather than papering over occasional Hypothesis failures.
"""

from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from mindtrace.domain.confidence import CalibrationLedger, CalibrationRecord, EnsembleObservation
from mindtrace.domain.enums import DecisionOutcome
from mindtrace.domain.ids import FactorId
from mindtrace.engines.confidence.compute import compute_confidence
from mindtrace.engines.confidence.config import DEFAULT_CONFIDENCE_CONFIG
from tests.support.confidence_fixtures import DECISION_EXAMPLE_1, DECISION_EXAMPLE_3

_KNOWN_IDS = tuple(FactorId(c.factor_id) for c in DECISION_EXAMPLE_1.contributions)

_n_eff_strategy = st.dictionaries(
    keys=st.sampled_from(_KNOWN_IDS),
    values=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
)


@st.composite
def ensemble_observations(draw: st.DrawFn) -> EnsembleObservation | None:
    if draw(st.booleans()) is False:
        return None
    n = draw(st.integers(min_value=2, max_value=5))
    score_strategy = st.floats(min_value=-1.0, max_value=1.0, allow_nan=False)
    scores = tuple(draw(score_strategy) for _ in range(n))
    labels = tuple(draw(st.sampled_from(list(DecisionOutcome))) for _ in range(n))
    return EnsembleObservation(scores=scores, labels=labels)


@given(n_eff=st.one_of(st.none(), _n_eff_strategy), ensemble=ensemble_observations())
@settings(max_examples=200)
def test_determinism_same_input_same_result(
    n_eff: dict[FactorId, float] | None, ensemble: EnsembleObservation | None
) -> None:
    """Same inputs + confidence config version => identical `C` (spec §06 §10)."""
    first = compute_confidence(DECISION_EXAMPLE_1, n_eff=n_eff, ensemble=ensemble)
    second = compute_confidence(DECISION_EXAMPLE_1, n_eff=n_eff, ensemble=ensemble)
    assert first.model_dump_json() == second.model_dump_json()


@given(n_eff=st.one_of(st.none(), _n_eff_strategy), ensemble=ensemble_observations())
@settings(max_examples=200)
def test_confidence_always_in_unit_interval(
    n_eff: dict[FactorId, float] | None, ensemble: EnsembleObservation | None
) -> None:
    """`0 <= C <= 1` for every valid input combination (spec §06 §5/§9)."""
    for decision in (DECISION_EXAMPLE_1, DECISION_EXAMPLE_3):
        result = compute_confidence(decision, n_eff=n_eff, ensemble=ensemble)
        assert 0.0 <= result.value <= 1.0
        assert 0.0 <= result.raw <= 1.0


@given(
    ensemble=ensemble_observations(),
    calibrated=st.booleans(),
)
@settings(max_examples=100)
def test_score_independence_flipping_sign_never_changes_confidence(
    ensemble: EnsembleObservation | None, calibrated: bool
) -> None:
    """`C` is invariant under negating `S` while holding margin/coverage/weights fixed -
    `compute_confidence` structurally cannot read `decision.score` at all."""
    calibration = (
        CalibrationLedger(
            domain_records=tuple(
                CalibrationRecord(predicted_confidence=0.6, correct=True) for _ in range(20)
            )
        )
        if calibrated
        else None
    )
    flipped = DECISION_EXAMPLE_1.model_copy(
        update={"score": -DECISION_EXAMPLE_1.score, "raw_score": -DECISION_EXAMPLE_1.raw_score}
    )
    original = compute_confidence(DECISION_EXAMPLE_1, ensemble=ensemble, calibration=calibration)
    negated = compute_confidence(flipped, ensemble=ensemble, calibration=calibration)
    assert original.value == negated.value
    assert original.raw == negated.raw


@given(n_eff=_n_eff_strategy)
@settings(max_examples=100)
def test_evidence_sufficiency_monotone_in_n_eff_scaling(n_eff: dict[FactorId, float]) -> None:
    """Uniformly scaling every `n_eff` value up never *decreases* `evidence_sufficiency` -
    the formula's own saturating-exponential shape guarantees this (spec §06 §4.1)."""
    doubled = {fid: value * 2.0 for fid, value in n_eff.items()}
    base = compute_confidence(DECISION_EXAMPLE_1, n_eff=n_eff)
    scaled = compute_confidence(DECISION_EXAMPLE_1, n_eff=doubled)
    assert scaled.inputs.evidence_sufficiency >= base.inputs.evidence_sufficiency - 1e-12


@given(n_eff=st.one_of(st.none(), _n_eff_strategy), ensemble=ensemble_observations())
@settings(max_examples=100)
def test_missing_signals_are_never_silently_favourable(
    n_eff: dict[FactorId, float] | None, ensemble: EnsembleObservation | None
) -> None:
    """No calibration ledger and no extraction signal are supplied anywhere in this test -
    both must always come back explicitly "unavailable", never a default good value."""
    result = compute_confidence(DECISION_EXAMPLE_1, n_eff=n_eff, ensemble=ensemble)
    assert result.inputs.historical_calibration is None
    assert result.inputs.calibrated == "false"
    assert result.inputs.extraction_entropy is None
    assert result.inputs.extraction_path == "unavailable"


@given(n_eff=st.one_of(st.none(), _n_eff_strategy), ensemble=ensemble_observations())
@settings(max_examples=100)
def test_weights_used_always_sum_to_one(
    n_eff: dict[FactorId, float] | None, ensemble: EnsembleObservation | None
) -> None:
    result = compute_confidence(DECISION_EXAMPLE_1, n_eff=n_eff, ensemble=ensemble)
    assert math.isclose(sum(result.weights_used.values()), 1.0, abs_tol=1e-9)


@given(n_eff=st.one_of(st.none(), _n_eff_strategy), ensemble=ensemble_observations())
@settings(max_examples=100)
def test_c_never_equals_abs_s(
    n_eff: dict[FactorId, float] | None, ensemble: EnsembleObservation | None
) -> None:
    """The M4 prompt's absolute invariant, across arbitrary inputs - not just the golden set."""
    for decision in (DECISION_EXAMPLE_1, DECISION_EXAMPLE_3):
        result = compute_confidence(decision, n_eff=n_eff, ensemble=ensemble)
        assert not math.isclose(result.value, abs(decision.score), abs_tol=1e-12)


def test_default_config_c_min_is_a_sanity_reference() -> None:
    """Not a property test - a guard that the config used above still matches spec/06 §3."""
    assert DEFAULT_CONFIDENCE_CONFIG.c_min == 0.35
