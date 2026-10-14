"""Tests for deterministic parallel-twin re-parametrisation (M10; ADR-007)."""

from __future__ import annotations

import itertools
import statistics

import pytest

from mindtrace.domain.decision import FactorReading, FactorVector, WeightVector
from mindtrace.domain.enums import ScaleLevel
from mindtrace.domain.factors import load_factor_taxonomy
from mindtrace.domain.ids import FactorId
from mindtrace.domain.simulation import TwinConfigResult
from mindtrace.domain.traits import load_trait_model
from mindtrace.domain.twins import BASE_TWIN_ID, TwinDefinition, load_twin_table
from mindtrace.engines.mcda.decide import decide
from mindtrace.engines.preference.prior import initial_posterior
from mindtrace.engines.preference.projection import project_effective_weights
from mindtrace.engines.simulation.parallel import (
    apply_twin_transform,
    ensemble_observation_from,
    run_twin_ensemble,
)

_TAXONOMY = load_factor_taxonomy()
_TRAIT_MODEL = load_trait_model(taxonomy=_TAXONOMY)
_TWIN_TABLE = load_twin_table(taxonomy=_TAXONOMY)
_POSTERIOR = initial_posterior(_TRAIT_MODEL)
_PREFERENCE = project_effective_weights(_POSTERIOR, _TRAIT_MODEL)

_CAREER = next(t for t in _TWIN_TABLE.twins if t.id == "career")


def _uniform_weights() -> WeightVector:
    ids = list(_TAXONOMY.core_ids)
    return WeightVector(weights=dict.fromkeys(ids, 1.0 / len(ids)))


def _mixed_factor_vector() -> FactorVector:
    """A non-uniform reading over the core factors - varied enough that twin weight
    shifts actually move the score (a uniform "everything high" reading makes every
    weight vector score almost identically, which would hide real disagreement)."""
    levels = [
        ScaleLevel.VERY_HIGH,
        ScaleLevel.HIGH,
        ScaleLevel.MODERATE,
        ScaleLevel.LOW,
        ScaleLevel.VERY_LOW,
    ]
    readings = {
        factor_id: FactorReading(level=levels[i % len(levels)], known=True)
        for i, factor_id in enumerate(sorted(_TAXONOMY.core_ids))
    }
    return FactorVector(readings=readings)


class TestApplyTwinTransform:
    def test_up_weighted_factors_increase_relative_to_untouched_ones(self) -> None:
        base = _uniform_weights()
        transformed = apply_twin_transform(base, _CAREER, lam=0.35)
        untouched = next(f for f in base.weights if f not in _CAREER.up and f not in _CAREER.down)
        for factor_id in _CAREER.up:
            assert transformed.weights[factor_id] > transformed.weights[untouched]

    def test_down_weighted_factors_decrease_relative_to_untouched_ones(self) -> None:
        base = _uniform_weights()
        transformed = apply_twin_transform(base, _CAREER, lam=0.35)
        untouched = next(f for f in base.weights if f not in _CAREER.up and f not in _CAREER.down)
        for factor_id in _CAREER.down:
            assert transformed.weights[factor_id] < transformed.weights[untouched]

    def test_untouched_factors_keep_the_same_relative_share(self) -> None:
        base = _uniform_weights()
        transformed = apply_twin_transform(base, _CAREER, lam=0.35)
        untouched = [f for f in base.weights if f not in _CAREER.up and f not in _CAREER.down]
        shares = {transformed.weights[f] for f in untouched}
        assert len(shares) == 1  # every untouched factor shifted by the same renorm factor

    def test_result_sums_to_one(self) -> None:
        transformed = apply_twin_transform(_uniform_weights(), _CAREER, lam=0.35)
        assert sum(transformed.weights.values()) == pytest.approx(1.0, abs=1e-9)

    def test_zero_lambda_is_the_identity(self) -> None:
        base = _uniform_weights()
        transformed = apply_twin_transform(base, _CAREER, lam=0.0)
        for factor_id, weight in base.weights.items():
            assert transformed.weights[factor_id] == pytest.approx(weight, abs=1e-12)

    def test_a_twin_with_no_shifts_is_also_the_identity(self) -> None:
        empty_twin = TwinDefinition(id="noop", label="No-op", up=(), down=())
        base = _uniform_weights()
        transformed = apply_twin_transform(base, empty_twin, lam=0.35)
        for factor_id, weight in base.weights.items():
            assert transformed.weights[factor_id] == pytest.approx(weight, abs=1e-12)

    def test_career_you_still_reflects_the_user(self) -> None:
        """ADR-007: 'Career-You of a stability-loving person is still noticeably
        stability-leaning' - anchored to w*, not an archetype."""
        strongly_stable = FactorId("stability")
        ids = list(_TAXONOMY.core_ids)
        raw = dict.fromkeys(ids, 0.02)
        raw[strongly_stable] = 1.0 - 0.02 * (len(ids) - 1)
        base = WeightVector(weights=raw)

        transformed = apply_twin_transform(base, _CAREER, lam=0.35)
        uniform_share = 1.0 / len(ids)
        # stability is in Career-You's `down` list, yet a person whose base weight on
        # it dominates everything else must still end up well above the uniform
        # baseline after only a 35% shift - this is "still that person", not a
        # generic archetype that would flatten it to near-zero.
        assert transformed.weights[strongly_stable] > uniform_share * 5


class TestEnsembleDisagreementMonotonicInLambda:
    def test_disagreement_monotonic_in_lambda(self) -> None:
        """ADR-007's own named test: larger lambda -> more twin-score dispersion."""
        factors_a = _mixed_factor_vector()
        base_decision = decide(_TAXONOMY, _PREFERENCE.weights, factors_a, _PREFERENCE.dispositions)
        base_result = TwinConfigResult(
            twin=BASE_TWIN_ID, preference=_PREFERENCE, decision=base_decision
        )

        dispersions = []
        for lam in (0.0, 0.15, 0.35, 0.6):
            results = run_twin_ensemble(
                _TAXONOMY,
                _PREFERENCE,
                base_result,
                _TWIN_TABLE.twins,
                factors_a,
                lam=lam,
            )
            scores = [r.decision.score for r in results]
            dispersions.append(statistics.pstdev(scores))

        for earlier, later in itertools.pairwise(dispersions):
            assert later >= earlier - 1e-12


class TestRunTwinEnsemble:
    def test_parallel_twins_are_distinct(self) -> None:
        """ADR-007's own named test: the twins are not all the same, and are not
        copies of the base twin's weights either."""
        factors_a = _mixed_factor_vector()
        base_decision = decide(_TAXONOMY, _PREFERENCE.weights, factors_a, _PREFERENCE.dispositions)
        base_result = TwinConfigResult(
            twin=BASE_TWIN_ID, preference=_PREFERENCE, decision=base_decision
        )
        results = run_twin_ensemble(
            _TAXONOMY, _PREFERENCE, base_result, _TWIN_TABLE.twins, factors_a, lam=0.35
        )
        weight_vectors = [tuple(sorted(r.preference.weights.weights.items())) for r in results]
        assert len(set(weight_vectors)) == len(weight_vectors)

    def test_base_result_is_reused_byte_identical(self) -> None:
        """Single-twin-compatibility: the base twin's own DecisionResult is never recomputed."""
        factors_a = _mixed_factor_vector()
        base_decision = decide(_TAXONOMY, _PREFERENCE.weights, factors_a, _PREFERENCE.dispositions)
        base_result = TwinConfigResult(
            twin=BASE_TWIN_ID, preference=_PREFERENCE, decision=base_decision
        )
        results = run_twin_ensemble(
            _TAXONOMY, _PREFERENCE, base_result, _TWIN_TABLE.twins, factors_a, lam=0.35
        )
        assert results[0] is base_result
        assert results[0].decision is base_decision

    def test_returns_base_plus_every_named_twin(self) -> None:
        factors_a = _mixed_factor_vector()
        base_decision = decide(_TAXONOMY, _PREFERENCE.weights, factors_a, _PREFERENCE.dispositions)
        base_result = TwinConfigResult(
            twin=BASE_TWIN_ID, preference=_PREFERENCE, decision=base_decision
        )
        results = run_twin_ensemble(
            _TAXONOMY, _PREFERENCE, base_result, _TWIN_TABLE.twins, factors_a, lam=0.35
        )
        assert [r.twin for r in results] == ["base", "career", "safe", "dream", "future"]

    def test_dispositions_are_identical_across_every_twin(self) -> None:
        """Dispositions are the user's own, never varied per twin (ADR-007 only shifts weights)."""
        factors_a = _mixed_factor_vector()
        base_decision = decide(_TAXONOMY, _PREFERENCE.weights, factors_a, _PREFERENCE.dispositions)
        base_result = TwinConfigResult(
            twin=BASE_TWIN_ID, preference=_PREFERENCE, decision=base_decision
        )
        results = run_twin_ensemble(
            _TAXONOMY, _PREFERENCE, base_result, _TWIN_TABLE.twins, factors_a, lam=0.35
        )
        for result in results:
            assert result.preference.dispositions == _PREFERENCE.dispositions

    def test_rejects_a_base_decision_not_labelled_base(self) -> None:
        factors_a = _mixed_factor_vector()
        base_decision = decide(_TAXONOMY, _PREFERENCE.weights, factors_a, _PREFERENCE.dispositions)
        wrong_label = TwinConfigResult(
            twin="career", preference=_PREFERENCE, decision=base_decision
        )
        with pytest.raises(ValueError, match="base"):
            run_twin_ensemble(
                _TAXONOMY, _PREFERENCE, wrong_label, _TWIN_TABLE.twins, factors_a, lam=0.35
            )


class TestEnsembleObservationFrom:
    def test_projects_scores_and_labels_in_order(self) -> None:
        factors_a = _mixed_factor_vector()
        base_decision = decide(_TAXONOMY, _PREFERENCE.weights, factors_a, _PREFERENCE.dispositions)
        base_result = TwinConfigResult(
            twin=BASE_TWIN_ID, preference=_PREFERENCE, decision=base_decision
        )
        results = run_twin_ensemble(
            _TAXONOMY, _PREFERENCE, base_result, _TWIN_TABLE.twins, factors_a, lam=0.35
        )
        observation = ensemble_observation_from(results)
        assert observation.scores == tuple(r.decision.score for r in results)
        assert observation.labels == tuple(r.decision.label for r in results)
