"""Golden tests for the preference engine (M4 s22).

`docs/adr/ADR-005-bayesian-preference-estimation.md` and spec/04 have no
hand-worked numeric examples the way spec/05 §9 does (a 19-dimensional
coupled Newton system has no simple closed form). These are therefore
**implementation fixtures**: each one's *qualitative* claim (which direction
`mu` moves, that `sigma` shrinks, that a symmetric pair stays exactly equal)
is independently derived and asserted before the exact float64 output is
pinned as a regression baseline - never an opaque number copied from a run
with no derivation. Regenerate after a deliberate, reviewed change:

    MINDTRACE_GOLDEN_UPDATE=1 pytest tests/golden/test_preference_golden.py -q
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import pytest

from mindtrace.domain.enums import ChoiceOption
from mindtrace.domain.ids import FactorId
from mindtrace.domain.traits import PairwiseObservation, PreferencePosterior
from mindtrace.engines.preference.config import DEFAULT_PREFERENCE_CONFIG
from mindtrace.engines.preference.prior import initial_posterior
from mindtrace.engines.preference.update import (
    apply_disposition_observations,
    apply_pairwise_observations,
)
from tests.support.preference_fixtures import (
    TRAIT_MODEL,
    all_disposition_observations,
    all_pairwise_observations,
)

DATA_DIR = Path(__file__).parent / "data" / "preference_examples"
ABS_TOL = 1e-6

_SKILL_GROWTH = FactorId("skill_growth")
_FINANCIAL_RETURN = FactorId("financial_return")
_AUTONOMY = FactorId("autonomy")
_STABILITY = FactorId("stability")


def _assert_matches_golden(name: str, posterior: PreferencePosterior) -> None:
    path = DATA_DIR / f"{name}.json"
    actual = json.loads(posterior.model_dump_json())

    if os.environ.get("MINDTRACE_GOLDEN_UPDATE") == "1":
        path.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return

    assert path.exists(), f"{path} is missing - generate it once with MINDTRACE_GOLDEN_UPDATE=1"
    expected = json.loads(path.read_text(encoding="utf-8"))
    _assert_deep_close(actual, expected, path=name)


def _assert_deep_close(actual: Any, expected: Any, *, path: str) -> None:
    if isinstance(expected, dict):
        assert isinstance(actual, dict), path
        assert actual.keys() == expected.keys(), path
        for key in expected:
            _assert_deep_close(actual[key], expected[key], path=f"{path}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list), path
        assert len(actual) == len(expected), path
        for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
            _assert_deep_close(a, e, path=f"{path}[{i}]")
    elif isinstance(expected, float):
        assert math.isclose(actual, expected, abs_tol=ABS_TOL, rel_tol=0), (
            f"{path}: {actual!r} != {expected!r}"
        )
    else:
        assert actual == expected, path


class TestZeroObservations:
    """1. No evidence at all: the posterior must equal the prior exactly."""

    def test_matches_the_prior_exactly(self) -> None:
        posterior = initial_posterior(TRAIT_MODEL)
        for weight_spec in TRAIT_MODEL.weights:
            wp = posterior.weights[weight_spec.factor]
            assert wp.mu == weight_spec.prior.mu
            assert wp.sigma == weight_spec.prior.sigma
        _assert_matches_golden("zero_observations", posterior)


class TestOneObservation:
    """2. A single "skill_growth > financial_return" observation."""

    def test_moves_in_the_expected_direction_and_narrows(self) -> None:
        prior = initial_posterior(TRAIT_MODEL)
        obs = [
            PairwiseObservation(
                design={_SKILL_GROWTH: 1.0, _FINANCIAL_RETURN: -1.0}, outcome=1.0, weight=1.0
            )
        ]
        posterior = apply_pairwise_observations(prior, obs, DEFAULT_PREFERENCE_CONFIG)

        assert posterior.weights[_SKILL_GROWTH].mu > prior.weights[_SKILL_GROWTH].mu
        assert posterior.weights[_FINANCIAL_RETURN].mu < prior.weights[_FINANCIAL_RETURN].mu
        assert posterior.weights[_SKILL_GROWTH].sigma < prior.weights[_SKILL_GROWTH].sigma
        assert sum(w.mu for w in posterior.weights.values()) == pytest.approx(0.0, abs=1e-9)
        _assert_matches_golden("one_observation", posterior)


class TestRepeatedObservation:
    """3. The same observation five times: further and narrower than once."""

    def test_moves_further_than_a_single_observation(self) -> None:
        prior = initial_posterior(TRAIT_MODEL)
        single_obs = [
            PairwiseObservation(
                design={_SKILL_GROWTH: 1.0, _FINANCIAL_RETURN: -1.0}, outcome=1.0, weight=1.0
            )
        ]
        once = apply_pairwise_observations(prior, single_obs, DEFAULT_PREFERENCE_CONFIG)
        five_times = apply_pairwise_observations(prior, single_obs * 5, DEFAULT_PREFERENCE_CONFIG)

        assert five_times.weights[_SKILL_GROWTH].mu > once.weights[_SKILL_GROWTH].mu
        assert five_times.weights[_SKILL_GROWTH].sigma < once.weights[_SKILL_GROWTH].sigma
        _assert_matches_golden("repeated_observation", five_times)


class TestBalancedObservations:
    """4. Three "A>B" and three "B>A": evidence counted, but net movement stays small."""

    def test_stays_close_to_the_prior_but_still_narrows(self) -> None:
        prior = initial_posterior(TRAIT_MODEL)
        a_over_b = PairwiseObservation(
            design={_SKILL_GROWTH: 1.0, _FINANCIAL_RETURN: -1.0}, outcome=1.0, weight=1.0
        )
        b_over_a = PairwiseObservation(
            design={_SKILL_GROWTH: 1.0, _FINANCIAL_RETURN: -1.0}, outcome=0.0, weight=1.0
        )
        posterior = apply_pairwise_observations(
            prior, [a_over_b, b_over_a] * 3, DEFAULT_PREFERENCE_CONFIG
        )

        # Evidence is real (sigma still shrinks) even though it nets to a small move.
        assert posterior.weights[_SKILL_GROWTH].sigma < prior.weights[_SKILL_GROWTH].sigma
        assert posterior.weight_evidence_count[_SKILL_GROWTH] == 1
        _assert_matches_golden("balanced_observations", posterior)


class TestStronglyContradictoryEvidence:
    """5. Ten "A>B" and ten "B>A": far more evidence, still not discarded."""

    def test_narrows_further_than_the_balanced_case_but_still_stays_near_prior(self) -> None:
        prior = initial_posterior(TRAIT_MODEL)
        a_over_b = PairwiseObservation(
            design={_SKILL_GROWTH: 1.0, _FINANCIAL_RETURN: -1.0}, outcome=1.0, weight=1.0
        )
        b_over_a = PairwiseObservation(
            design={_SKILL_GROWTH: 1.0, _FINANCIAL_RETURN: -1.0}, outcome=0.0, weight=1.0
        )
        balanced = apply_pairwise_observations(
            prior, [a_over_b, b_over_a] * 3, DEFAULT_PREFERENCE_CONFIG
        )
        posterior = apply_pairwise_observations(
            prior, [a_over_b, b_over_a] * 10, DEFAULT_PREFERENCE_CONFIG
        )

        assert posterior.weights[_SKILL_GROWTH].sigma < balanced.weights[_SKILL_GROWTH].sigma
        _assert_matches_golden("strongly_contradictory", posterior)


class TestSymmetricPair:
    """6. `autonomy`/`stability` share an identical prior (traits.yaml: mu=0, sigma=1.5) -
    mirrored evidence must leave them exactly equal to each other."""

    def test_stays_exactly_equal_after_mirrored_evidence(self) -> None:
        prior = initial_posterior(TRAIT_MODEL)
        assert prior.weights[_AUTONOMY].mu == prior.weights[_STABILITY].mu
        assert prior.weights[_AUTONOMY].sigma == prior.weights[_STABILITY].sigma

        observations = [
            PairwiseObservation(design={_AUTONOMY: 1.0, _STABILITY: -1.0}, outcome=1.0, weight=1.0),
            PairwiseObservation(design={_AUTONOMY: -1.0, _STABILITY: 1.0}, outcome=1.0, weight=1.0),
        ]
        posterior = apply_pairwise_observations(prior, observations, DEFAULT_PREFERENCE_CONFIG)

        assert posterior.weights[_AUTONOMY].mu == pytest.approx(
            posterior.weights[_STABILITY].mu, abs=1e-9
        )
        _assert_matches_golden("symmetric_pair", posterior)


class TestAllTwentyFourInterviewAnswers:
    """7. Every pairwise (16) + disposition (8) item, all answered "A" - the full
    cold-start interview (spec/07 §6: "24 items total")."""

    def test_processes_all_24_items_and_keeps_the_gauge(self) -> None:
        prior = initial_posterior(TRAIT_MODEL)
        pairwise_obs = all_pairwise_observations(ChoiceOption.A)
        disposition_obs = all_disposition_observations(ChoiceOption.A)
        assert len(pairwise_obs) + len(disposition_obs) == 24

        with_weights = apply_pairwise_observations(prior, pairwise_obs, DEFAULT_PREFERENCE_CONFIG)
        posterior = apply_disposition_observations(
            with_weights, disposition_obs, DEFAULT_PREFERENCE_CONFIG
        )

        assert sum(w.mu for w in posterior.weights.values()) == pytest.approx(0.0, abs=1e-9)
        for factor_id, weight in posterior.weights.items():
            assert weight.sigma <= TRAIT_MODEL.weight_for(factor_id).prior.sigma
        _assert_matches_golden("all_24_interview_answers", posterior)


class TestPosteriorSerializationRoundTrip:
    """8. `PreferencePosterior` survives a JSON round-trip byte-for-byte."""

    def test_round_trips_through_json(self) -> None:
        prior = initial_posterior(TRAIT_MODEL)
        obs = [
            PairwiseObservation(
                design={_SKILL_GROWTH: 1.0, _FINANCIAL_RETURN: -1.0}, outcome=1.0, weight=1.0
            )
        ]
        posterior = apply_pairwise_observations(prior, obs, DEFAULT_PREFERENCE_CONFIG)
        disposition_obs = [
            all_disposition_observations(ChoiceOption.A)[0],
        ]
        posterior = apply_disposition_observations(
            posterior, disposition_obs, DEFAULT_PREFERENCE_CONFIG
        )

        dumped = posterior.model_dump_json()
        reconstructed = PreferencePosterior.model_validate_json(dumped)

        assert reconstructed == posterior
        assert reconstructed.model_dump_json() == dumped
        _assert_matches_golden("serialization_round_trip", posterior)

    def test_reconstructed_posterior_can_be_updated_further(self) -> None:
        prior = initial_posterior(TRAIT_MODEL)
        dumped = prior.model_dump_json()
        reconstructed = PreferencePosterior.model_validate_json(dumped)
        obs = [
            PairwiseObservation(
                design={_SKILL_GROWTH: 1.0, _FINANCIAL_RETURN: -1.0}, outcome=1.0, weight=1.0
            )
        ]
        result_from_original = apply_pairwise_observations(prior, obs, DEFAULT_PREFERENCE_CONFIG)
        result_from_reconstructed = apply_pairwise_observations(
            reconstructed, obs, DEFAULT_PREFERENCE_CONFIG
        )
        assert result_from_original == result_from_reconstructed
