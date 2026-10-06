"""Tests for turning a belief dispute into one M4 batch update (M9; spec/07 s4.1/s4.2 reused)."""

from __future__ import annotations

from tests.support.preference_fixtures import INTERVIEW_BANK, TAXONOMY, TRAIT_MODEL

from mindtrace.domain.enums import ChoiceOption
from mindtrace.engines.elicitation.dispute import DISPUTE_REPEAT_COUNT, apply_dispute
from mindtrace.engines.preference.config import DEFAULT_PREFERENCE_CONFIG
from mindtrace.engines.preference.interview import pairwise_observation_from_item
from mindtrace.engines.preference.prior import initial_posterior
from mindtrace.engines.preference.update import apply_pairwise_observations

_PAIRWISE_ITEM = INTERVIEW_BANK.pairwise[0]
_DISPOSITION_ITEM = INTERVIEW_BANK.disposition[0]
_PRIOR = initial_posterior(TRAIT_MODEL)


class TestApplyDisputePairwise:
    def test_moves_further_than_a_single_ordinary_answer(self) -> None:
        single_obs = [pairwise_observation_from_item(_PAIRWISE_ITEM, ChoiceOption.A, TAXONOMY)]
        once = apply_pairwise_observations(_PRIOR, single_obs, DEFAULT_PREFERENCE_CONFIG)
        disputed = apply_dispute(
            _PAIRWISE_ITEM,
            ChoiceOption.A,
            _PRIOR,
            taxonomy=TAXONOMY,
            config=DEFAULT_PREFERENCE_CONFIG,
        )

        varied_factor = next(iter(_PAIRWISE_ITEM.varied_factors))
        assert disputed.weights[varied_factor].sigma < once.weights[varied_factor].sigma

    def test_equivalent_to_repeating_the_same_observation_dispute_repeat_count_times(self) -> None:
        observation = pairwise_observation_from_item(_PAIRWISE_ITEM, ChoiceOption.B, TAXONOMY)
        expected = apply_pairwise_observations(
            _PRIOR, [observation] * DISPUTE_REPEAT_COUNT, DEFAULT_PREFERENCE_CONFIG
        )
        actual = apply_dispute(
            _PAIRWISE_ITEM,
            ChoiceOption.B,
            _PRIOR,
            taxonomy=TAXONOMY,
            config=DEFAULT_PREFERENCE_CONFIG,
        )
        assert actual == expected

    def test_never_fabricates_a_different_design_vector_or_outcome(self) -> None:
        """A dispute only ever changes the observation COUNT, never the design/outcome mapping
        the existing M8 adapter already produces - no new Bradley-Terry math."""
        design_from_adapter = pairwise_observation_from_item(
            _PAIRWISE_ITEM, ChoiceOption.A, TAXONOMY
        )
        disputed = apply_dispute(
            _PAIRWISE_ITEM,
            ChoiceOption.A,
            _PRIOR,
            taxonomy=TAXONOMY,
            config=DEFAULT_PREFERENCE_CONFIG,
        )
        replayed = apply_pairwise_observations(
            _PRIOR, [design_from_adapter] * DISPUTE_REPEAT_COUNT, DEFAULT_PREFERENCE_CONFIG
        )
        assert disputed == replayed

    def test_deterministic(self) -> None:
        first = apply_dispute(
            _PAIRWISE_ITEM,
            ChoiceOption.A,
            _PRIOR,
            taxonomy=TAXONOMY,
            config=DEFAULT_PREFERENCE_CONFIG,
        )
        second = apply_dispute(
            _PAIRWISE_ITEM,
            ChoiceOption.A,
            _PRIOR,
            taxonomy=TAXONOMY,
            config=DEFAULT_PREFERENCE_CONFIG,
        )
        assert first.model_dump(mode="json") == second.model_dump(mode="json")

    def test_indifferent_choice_is_accepted(self) -> None:
        disputed = apply_dispute(
            _PAIRWISE_ITEM, None, _PRIOR, taxonomy=TAXONOMY, config=DEFAULT_PREFERENCE_CONFIG
        )
        varied_factor = next(iter(_PAIRWISE_ITEM.varied_factors))
        assert disputed.weight_evidence_count[varied_factor] >= 1


class TestApplyDisputeDisposition:
    def test_moves_the_targeted_disposition(self) -> None:
        disputed = apply_dispute(
            _DISPOSITION_ITEM,
            _DISPOSITION_ITEM.keyed_option,
            _PRIOR,
            taxonomy=TAXONOMY,
            config=DEFAULT_PREFERENCE_CONFIG,
        )
        target = _DISPOSITION_ITEM.target
        assert disputed.disposition_evidence_count[target] == DISPUTE_REPEAT_COUNT

    def test_deterministic(self) -> None:
        first = apply_dispute(
            _DISPOSITION_ITEM,
            _DISPOSITION_ITEM.keyed_option,
            _PRIOR,
            taxonomy=TAXONOMY,
            config=DEFAULT_PREFERENCE_CONFIG,
        )
        second = apply_dispute(
            _DISPOSITION_ITEM,
            _DISPOSITION_ITEM.keyed_option,
            _PRIOR,
            taxonomy=TAXONOMY,
            config=DEFAULT_PREFERENCE_CONFIG,
        )
        assert first.model_dump(mode="json") == second.model_dump(mode="json")
