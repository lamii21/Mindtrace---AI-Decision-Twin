"""Reusable preference-engine fixtures, incl. the interview-item-bank adapter.

The adapter itself (`pairwise_observation_from_item`/`disposition_outcome`/...)
now lives in production code, `mindtrace.engines.preference.interview` (M8) -
this module re-exports it rather than keeping a second implementation, so the
spec/07 §7 "recovery" test and the "all 24 interview answers" golden scenario
exercise the exact same adapter production code calls.
"""

from __future__ import annotations

from mindtrace.domain.enums import ChoiceOption
from mindtrace.domain.factors import FactorTaxonomy, load_factor_taxonomy
from mindtrace.domain.interview import InterviewBank, load_interview_bank
from mindtrace.domain.traits import (
    DispositionObservation,
    PairwiseObservation,
    TraitModel,
    load_trait_model,
)
from mindtrace.engines.preference.interview import (
    disposition_observation_from_item,
    disposition_outcome,
    pairwise_design_vector,
    pairwise_observation_from_item,
)

TAXONOMY: FactorTaxonomy = load_factor_taxonomy()
TRAIT_MODEL: TraitModel = load_trait_model(taxonomy=TAXONOMY)
INTERVIEW_BANK: InterviewBank = load_interview_bank(taxonomy=TAXONOMY, trait_model=TRAIT_MODEL)

__all__ = [
    "INTERVIEW_BANK",
    "TAXONOMY",
    "TRAIT_MODEL",
    "all_disposition_observations",
    "all_pairwise_observations",
    "disposition_observation_from_item",
    "disposition_outcome",
    "pairwise_design_vector",
    "pairwise_observation_from_item",
]


def all_pairwise_observations(choose: ChoiceOption = ChoiceOption.A) -> list[PairwiseObservation]:
    """Every pairwise item in the bank, all answered the same fixed way.

    A simple, fully-deterministic synthetic respondent for golden/property fixtures.
    """
    return [
        pairwise_observation_from_item(item, choose, TAXONOMY) for item in INTERVIEW_BANK.pairwise
    ]


def all_disposition_observations(
    choose: ChoiceOption = ChoiceOption.A,
) -> list[DispositionObservation]:
    return [disposition_observation_from_item(item, choose) for item in INTERVIEW_BANK.disposition]
