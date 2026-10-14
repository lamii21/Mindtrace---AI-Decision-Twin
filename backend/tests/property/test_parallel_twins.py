"""Property-based tests for M10's parallel-twin engine (ADR-007; roadmap s24).

Every property here is one the implementation actually guarantees by
construction - determinism, a closed (sum-to-1, non-negative, finite) weight
simplex after any twin transform, and order-independence of the synthesis
vote over a *fixed* set of twin results - not a re-verification of M3's own
MCDA mathematics (that already has its own property suite in
``test_mcda.py``) or of M4's confidence bounds (``test_confidence.py``
already hypothesis-tests ``compute_confidence`` over arbitrary
``EnsembleObservation``s, including the now-real ensemble path this engine
feeds it).
"""

from __future__ import annotations

import itertools
import math

from hypothesis import given, settings
from hypothesis import strategies as st

from mindtrace.domain.decision import DispositionInputs, FactorReading, FactorVector, WeightVector
from mindtrace.domain.enums import DecisionOutcome, ScaleLevel
from mindtrace.domain.simulation import TwinConfigResult
from mindtrace.domain.traits import load_trait_model
from mindtrace.domain.twins import BASE_TWIN_ID, load_twin_table
from mindtrace.engines.debate.synthesis import synthesize
from mindtrace.engines.mcda.decide import decide
from mindtrace.engines.preference.prior import initial_posterior
from mindtrace.engines.preference.projection import project_effective_weights
from mindtrace.engines.simulation.parallel import apply_twin_transform, run_twin_ensemble
from tests.support.mcda_fixtures import TAXONOMY
from tests.support.twin_fixtures import twin_result_with

_TRAIT_MODEL = load_trait_model(taxonomy=TAXONOMY)
_TWIN_TABLE = load_twin_table(taxonomy=TAXONOMY)
_PREFERENCE = project_effective_weights(initial_posterior(_TRAIT_MODEL), _TRAIT_MODEL)
_CORE_IDS = tuple(sorted(TAXONOMY.core_ids))
_LEVELS = tuple(ScaleLevel)


@st.composite
def weight_vectors(draw: st.DrawFn) -> WeightVector:
    """A valid `WeightVector` over every core factor - positive raw draws, normalised to 1."""
    raw = [draw(st.floats(min_value=0.01, max_value=1.0, allow_nan=False)) for _ in _CORE_IDS]
    total = sum(raw)
    return WeightVector(weights=dict(zip(_CORE_IDS, (v / total for v in raw), strict=True)))


@st.composite
def factor_vectors(draw: st.DrawFn) -> FactorVector:
    """A `FactorVector` with every core factor known, at a random level each."""
    readings = {
        factor_id: FactorReading(level=draw(st.sampled_from(_LEVELS)), known=True)
        for factor_id in _CORE_IDS
    }
    return FactorVector(readings=readings)


_dispositions_strategy = st.builds(
    DispositionInputs,
    risk_tolerance=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    time_discount=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    ambiguity_aversion=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    effort_tolerance=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)


class TestApplyTwinTransformIsAClosedSimplex:
    @given(base=weight_vectors(), lam=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    @settings(max_examples=100)
    def test_result_sums_to_one_and_is_finite_and_non_negative(
        self, base: WeightVector, lam: float
    ) -> None:
        for twin in _TWIN_TABLE.twins:
            transformed = apply_twin_transform(base, twin, lam=lam)
            values = list(transformed.weights.values())
            assert all(math.isfinite(v) for v in values)
            assert all(v >= 0.0 for v in values)
            assert math.isclose(sum(values), 1.0, rel_tol=1e-9, abs_tol=1e-9)


class TestRunTwinEnsembleIsDeterministic:
    @given(factors=factor_vectors(), dispositions=_dispositions_strategy)
    @settings(max_examples=25)
    def test_identical_inputs_produce_identical_scores(
        self, factors: FactorVector, dispositions: DispositionInputs
    ) -> None:
        base_decision = decide(TAXONOMY, _PREFERENCE.weights, factors, dispositions)
        base_result = TwinConfigResult(
            twin=BASE_TWIN_ID, preference=_PREFERENCE, decision=base_decision
        )

        first = run_twin_ensemble(
            TAXONOMY, _PREFERENCE, base_result, _TWIN_TABLE.twins, factors, lam=_TWIN_TABLE.lambda_
        )
        second = run_twin_ensemble(
            TAXONOMY, _PREFERENCE, base_result, _TWIN_TABLE.twins, factors, lam=_TWIN_TABLE.lambda_
        )

        assert [r.decision.score for r in first] == [r.decision.score for r in second]
        assert [r.decision.label for r in first] == [r.decision.label for r in second]
        for result in first:
            assert math.isfinite(result.decision.score)


class TestSynthesisIsOrderIndependent:
    """`synthesize` tallies votes and variance over a *set* of twin results - the order
    its caller happens to list them in must never change the outcome."""

    @given(
        labels=st.lists(st.sampled_from(list(DecisionOutcome)), min_size=1, max_size=4),
    )
    @settings(max_examples=50)
    def test_shuffling_the_non_base_twins_does_not_change_the_synthesis(
        self, labels: list[DecisionOutcome]
    ) -> None:
        base = twin_result_with(
            twin=BASE_TWIN_ID, contributions={"a": 1.0}, label=DecisionOutcome.ACCEPT
        )
        others = [
            twin_result_with(twin=f"t{i}", contributions={"a": float(i)}, label=label)
            for i, label in enumerate(labels)
        ]

        baseline = synthesize([base, *others], base_twin_id=BASE_TWIN_ID)
        for permutation in itertools.islice(itertools.permutations(others), 6):
            shuffled = synthesize([base, *permutation], base_twin_id=BASE_TWIN_ID)
            assert shuffled.recommended_label == baseline.recommended_label
            assert shuffled.margin == baseline.margin
            assert shuffled.vote_tally == baseline.vote_tally
            assert shuffled.label_consensus == baseline.label_consensus
            assert set(shuffled.conflict_axis) == set(baseline.conflict_axis)
