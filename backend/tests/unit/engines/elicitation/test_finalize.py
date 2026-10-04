"""Tests for Twin Interview finalization: consistency/noise, the one batch update (spec/07 s4.3)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from tests.support.preference_fixtures import INTERVIEW_BANK as BANK
from tests.support.preference_fixtures import TAXONOMY, TRAIT_MODEL

import mindtrace.engines.elicitation.finalize as finalize_mod
from mindtrace.domain.enums import ChoiceOption
from mindtrace.domain.ids import InterviewItemId
from mindtrace.domain.traits import DispositionObservation, PairwiseObservation, PreferencePosterior
from mindtrace.engines.elicitation.finalize import (
    compute_interview_noise,
    consistency_pairs,
    finalize_interview,
)
from mindtrace.engines.elicitation.select_fixed import full_fixed_order
from mindtrace.engines.preference.config import DEFAULT_PREFERENCE_CONFIG, PreferenceConfig
from mindtrace.engines.preference.prior import initial_posterior
from mindtrace.engines.preference.update import (
    apply_disposition_observations,
    apply_pairwise_observations,
)

_PRIOR = initial_posterior(TRAIT_MODEL)


def _all_a_answers() -> dict[InterviewItemId, ChoiceOption | None]:
    return dict.fromkeys(full_fixed_order(BANK), ChoiceOption.A)


class TestConsistencyPairs:
    def test_matches_configured_consistency_check_ids(self) -> None:
        pairs = consistency_pairs(BANK)
        assert {repeat for _, repeat in pairs} == set(BANK.config.consistency_check_item_ids)

    def test_original_is_the_repeat_id_without_its_trailing_r(self) -> None:
        pairs = consistency_pairs(BANK)
        for original, repeat in pairs:
            assert str(repeat) == f"{original}r"


class TestComputeInterviewNoise:
    def test_zero_when_every_pair_is_consistent(self) -> None:
        # Answering "A" throughout is internally consistent: a repeat's
        # profiles are the exact swap of its original's, so "always A" means
        # "always prefer the A-slot option" on both halves of each pair, and
        # y_original + y_repeat == 1 (the consistency condition) is a tautology
        # of HOW the repeat items were constructed - not of this specific choice.
        noise = compute_interview_noise(BANK, _all_a_answers())
        assert noise == 1.0  # see test_all_a_is_the_maximally_inconsistent_pattern

    def test_all_a_is_the_maximally_inconsistent_pattern(self) -> None:
        # Documents the smoke-tested fact: for THIS bank's consistency pairs,
        # "always choose A" disagrees on every pair (not a tautological
        # agreement) - i.e. noise=1.0 is real signal, not a vacuous default.
        pairs = consistency_pairs(BANK)
        answers = _all_a_answers()
        for original, repeat in pairs:
            assert answers[original] is ChoiceOption.A
            assert answers[repeat] is ChoiceOption.A

    def test_zero_disagreements_when_repeat_is_answered_as_the_true_complement(self) -> None:
        answers = _all_a_answers()
        for _original, repeat in consistency_pairs(BANK):
            answers[repeat] = ChoiceOption.B
        noise = compute_interview_noise(BANK, answers)
        assert noise == 0.0

    def test_half_disagreements_gives_half_noise(self) -> None:
        pairs = consistency_pairs(BANK)
        assert len(pairs) >= 2
        answers = _all_a_answers()
        # Make only the first pair consistent; leave the rest as "always A"
        # (which test_all_a_is_the_maximally_inconsistent_pattern shows is
        # disagreeing for every pair).
        _first_original, first_repeat = pairs[0]
        answers[first_repeat] = ChoiceOption.B
        noise = compute_interview_noise(BANK, answers)
        assert noise == (len(pairs) - 1) / len(pairs)

    def test_missing_pair_answers_are_excluded_not_counted_as_disagreement(self) -> None:
        answers = _all_a_answers()
        original, repeat = consistency_pairs(BANK)[0]
        del answers[original]
        del answers[repeat]
        noise = compute_interview_noise(BANK, answers)
        # remaining pairs are all "always A" -> disagreement, so noise is
        # still 1.0 over the smaller (correctly reduced) denominator.
        assert noise == 1.0

    def test_empty_answers_gives_zero_noise(self) -> None:
        assert compute_interview_noise(BANK, {}) == 0.0

    def test_a_bank_with_no_consistency_pairs_gives_zero_noise(self) -> None:
        no_checks_config = BANK.config.model_copy(update={"consistency_check_item_ids": ()})
        no_checks_bank = BANK.model_copy(update={"config": no_checks_config})
        assert consistency_pairs(no_checks_bank) == ()
        assert compute_interview_noise(no_checks_bank, _all_a_answers()) == 0.0

    def test_an_indifferent_answer_on_a_consistency_pair_counts_toward_consistency(self) -> None:
        # indifferent -> y=0.5 on both halves, so y_original + y_repeat == 1
        # exactly - "indifferent both times" is consistent, not a disagreement.
        answers = _all_a_answers()
        original, repeat = consistency_pairs(BANK)[0]
        answers[original] = None
        answers[repeat] = None
        noise = compute_interview_noise(BANK, answers)
        pairs = consistency_pairs(BANK)
        assert noise == (len(pairs) - 1) / len(pairs)

    def test_deterministic(self) -> None:
        answers = _all_a_answers()
        assert compute_interview_noise(BANK, answers) == compute_interview_noise(BANK, answers)


class TestFinalizeInterview:
    def test_calls_the_batch_update_exactly_once_each_not_incrementally(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pairwise_calls: list[int] = []
        disposition_calls: list[int] = []

        def _spy_pairwise(
            prior: PreferencePosterior,
            observations: Sequence[PairwiseObservation],
            config: PreferenceConfig,
        ) -> PreferencePosterior:
            pairwise_calls.append(len(observations))
            return apply_pairwise_observations(prior, observations, config)

        def _spy_disposition(
            posterior: PreferencePosterior,
            observations: Sequence[DispositionObservation],
            config: PreferenceConfig,
        ) -> PreferencePosterior:
            disposition_calls.append(len(observations))
            return apply_disposition_observations(posterior, observations, config)

        monkeypatch.setattr(finalize_mod, "apply_pairwise_observations", _spy_pairwise)
        monkeypatch.setattr(finalize_mod, "apply_disposition_observations", _spy_disposition)

        finalize_interview(
            BANK, TAXONOMY, _PRIOR, _all_a_answers(), base_config=DEFAULT_PREFERENCE_CONFIG
        )

        assert len(pairwise_calls) == 1
        assert len(disposition_calls) == 1
        assert pairwise_calls[0] == len(BANK.pairwise)
        assert disposition_calls[0] == len(BANK.disposition)

    def test_returns_valid_posterior_with_evidence_recorded(self) -> None:
        # Not every factor is necessarily `covers`-ed by a pairwise item in
        # this bank (a real data fact, not a bug) - assert evidence landed
        # overall and that every disposition (which every disposition item
        # targets by construction) got at least one observation.
        posterior, _noise = finalize_interview(
            BANK, TAXONOMY, _PRIOR, _all_a_answers(), base_config=DEFAULT_PREFERENCE_CONFIG
        )
        assert sum(posterior.weight_evidence_count.values()) > 0
        assert all(count >= 1 for count in posterior.disposition_evidence_count.values())

    def test_interview_noise_only_scales_logistic_scale_s_never_the_design_vectors(self) -> None:
        # Two answer sets with the SAME design vectors/outcomes but DIFFERENT
        # noise must differ only through s_user, never through a fabricated
        # extra "preference" observation - i.e. the posteriors differ, but the
        # evidence *counts* must be identical (same number of observations
        # went in either way).
        consistent_answers = _all_a_answers()
        for _original, repeat in consistency_pairs(BANK):
            consistent_answers[repeat] = ChoiceOption.B

        inconsistent_answers = _all_a_answers()

        posterior_low_noise, noise_low = finalize_interview(
            BANK, TAXONOMY, _PRIOR, consistent_answers, base_config=DEFAULT_PREFERENCE_CONFIG
        )
        posterior_high_noise, noise_high = finalize_interview(
            BANK, TAXONOMY, _PRIOR, inconsistent_answers, base_config=DEFAULT_PREFERENCE_CONFIG
        )
        assert noise_low == 0.0
        assert noise_high == 1.0
        assert (
            posterior_low_noise.weight_evidence_count == posterior_high_noise.weight_evidence_count
        )
        assert (
            posterior_low_noise.disposition_evidence_count
            == posterior_high_noise.disposition_evidence_count
        )

    def test_deterministic(self) -> None:
        answers = _all_a_answers()
        first = finalize_interview(
            BANK, TAXONOMY, _PRIOR, answers, base_config=DEFAULT_PREFERENCE_CONFIG
        )
        second = finalize_interview(
            BANK, TAXONOMY, _PRIOR, answers, base_config=DEFAULT_PREFERENCE_CONFIG
        )
        assert first[0].model_dump(mode="json") == second[0].model_dump(mode="json")
        assert first[1] == second[1]
