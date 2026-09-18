"""Property-based tests for `project_effective_weights` (M6-A §19)."""

from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from mindtrace.domain.ids import DispositionId
from mindtrace.domain.traits import DispositionPosterior, PreferencePosterior, WeightPosterior
from mindtrace.engines.preference.config import PROJECTION_VERSION
from mindtrace.engines.preference.prior import initial_posterior
from mindtrace.engines.preference.projection import project_effective_weights
from tests.support.preference_fixtures import TRAIT_MODEL

_mu_strategy = st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False)
_sigma_strategy = st.floats(min_value=0.05, max_value=5.0, allow_nan=False, allow_infinity=False)
_alpha_beta_strategy = st.floats(
    min_value=0.1, max_value=50.0, allow_nan=False, allow_infinity=False
)


@st.composite
def arbitrary_valid_posteriors(draw: st.DrawFn) -> PreferencePosterior:
    """A `PreferencePosterior` with every core weight/disposition perturbed to an
    arbitrary but finite, individually-valid value - built by copying
    `initial_posterior`'s own structure (evidence counts, extended-factor
    posteriors) so only the fields this test cares about vary."""
    base = initial_posterior(TRAIT_MODEL)
    new_weights = dict(base.weights)
    for factor_id in TRAIT_MODEL.core_weight_factor_ids:
        new_weights[factor_id] = WeightPosterior(
            factor=factor_id, mu=draw(_mu_strategy), sigma=draw(_sigma_strategy)
        )
    new_dispositions = dict(base.dispositions)
    for disposition_id in (
        DispositionId("risk_tolerance"),
        DispositionId("time_discount"),
        DispositionId("ambiguity_aversion"),
        DispositionId("effort_tolerance"),
    ):
        new_dispositions[disposition_id] = DispositionPosterior(
            id=disposition_id, alpha=draw(_alpha_beta_strategy), beta=draw(_alpha_beta_strategy)
        )
    return base.model_copy(update={"weights": new_weights, "dispositions": new_dispositions})


@given(posterior=arbitrary_valid_posteriors())
@settings(max_examples=100)
def test_projection_is_deterministic(posterior: PreferencePosterior) -> None:
    first = project_effective_weights(posterior, TRAIT_MODEL)
    second = project_effective_weights(posterior, TRAIT_MODEL)
    assert first.model_dump_json() == second.model_dump_json()


@given(posterior=arbitrary_valid_posteriors())
@settings(max_examples=100)
def test_projection_does_not_mutate_the_posterior(posterior: PreferencePosterior) -> None:
    before = posterior.model_dump_json()
    project_effective_weights(posterior, TRAIT_MODEL)
    after = posterior.model_dump_json()
    assert before == after


@given(posterior=arbitrary_valid_posteriors())
@settings(max_examples=100)
def test_all_projected_weights_are_finite(posterior: PreferencePosterior) -> None:
    snapshot = project_effective_weights(posterior, TRAIT_MODEL)
    for value in snapshot.weights.weights.values():
        assert math.isfinite(value)


@given(posterior=arbitrary_valid_posteriors())
@settings(max_examples=100)
def test_all_projected_dispositions_are_finite_and_in_unit_range(
    posterior: PreferencePosterior,
) -> None:
    snapshot = project_effective_weights(posterior, TRAIT_MODEL)
    for value in (
        snapshot.dispositions.risk_tolerance,
        snapshot.dispositions.time_discount,
        snapshot.dispositions.ambiguity_aversion,
        snapshot.dispositions.effort_tolerance,
    ):
        assert math.isfinite(value)
        assert 0.0 <= value <= 1.0


@given(posterior=arbitrary_valid_posteriors())
@settings(max_examples=100)
def test_weights_sum_to_one(posterior: PreferencePosterior) -> None:
    """`WeightVector`'s own construction-time validator already enforces this
    (spec/05 §2a) - this property test confirms the projection never produces
    a value that validator would reject, across arbitrary finite posteriors."""
    snapshot = project_effective_weights(posterior, TRAIT_MODEL)
    total = sum(snapshot.weights.weights.values())
    assert math.isclose(total, 1.0, abs_tol=1e-6)


@given(posterior=arbitrary_valid_posteriors())
@settings(max_examples=50)
def test_schema_version_is_preserved(posterior: PreferencePosterior) -> None:
    snapshot = project_effective_weights(posterior, TRAIT_MODEL)
    assert snapshot.trait_schema_version == posterior.trait_schema_version
    assert snapshot.trait_schema_version == TRAIT_MODEL.version


@given(posterior=arbitrary_valid_posteriors())
@settings(max_examples=50)
def test_projection_version_is_always_explicit(posterior: PreferencePosterior) -> None:
    snapshot = project_effective_weights(posterior, TRAIT_MODEL)
    assert snapshot.projection_version == PROJECTION_VERSION
    assert snapshot.projection_version != "latest"


@given(posterior=arbitrary_valid_posteriors())
@settings(max_examples=50)
def test_weights_cover_exactly_the_core_taxonomy(posterior: PreferencePosterior) -> None:
    snapshot = project_effective_weights(posterior, TRAIT_MODEL)
    assert set(snapshot.weights.weights) == set(TRAIT_MODEL.core_weight_factor_ids)
