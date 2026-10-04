"""Parity test: `engines/preference/interview.py` vs. its pre-promotion test-only ancestor (M8).

Before M8, the interview-answer -> observation adapter
(`pairwise_observation_from_item`/`disposition_outcome`/...) lived only in
`tests/support/preference_fixtures.py` (commit 5aab2d3). M8 promotes it to
production code and the fixture module now re-exports from there instead of
keeping a second implementation - but promotion must be a pure move, never a
silent rewrite. This file freezes a verbatim copy of that pre-promotion
implementation and asserts the promoted production functions return
byte-identical output for every item in the real bank, across every possible
choice, so a behavioural drift during promotion would fail loudly here.
"""

from __future__ import annotations

from tests.support.preference_fixtures import INTERVIEW_BANK, TAXONOMY

from mindtrace.domain.decision import DispositionInputs
from mindtrace.domain.enums import ChoiceOption
from mindtrace.domain.factors import FactorTaxonomy
from mindtrace.domain.ids import DispositionId, FactorId
from mindtrace.domain.interview import DispositionItem, PairwiseItem
from mindtrace.domain.traits import DispositionObservation, PairwiseObservation
from mindtrace.engines.mcda.config import DEFAULT_MCDA_CONFIG
from mindtrace.engines.mcda.normalize import normalize_factor
from mindtrace.engines.preference.interview import (
    disposition_observation_from_item,
    disposition_outcome,
    pairwise_design_vector,
    pairwise_observation_from_item,
)

# --- verbatim pre-promotion reference (commit 5aab2d3's preference_fixtures.py) ---

_REF_NEUTRAL = DispositionInputs.neutral()
_REF_INVERTED_DISPOSITIONS = frozenset(
    {DispositionId("time_discount"), DispositionId("ambiguity_aversion")}
)


def _ref_neutral_normalized(taxonomy: FactorTaxonomy, factor_id: FactorId, level: object) -> float:
    spec = taxonomy.get(factor_id)
    anchor = spec.anchor_for(level)  # type: ignore[arg-type]
    return normalize_factor(spec, anchor, _REF_NEUTRAL, DEFAULT_MCDA_CONFIG)


def _ref_pairwise_design_vector(
    item: PairwiseItem, taxonomy: FactorTaxonomy
) -> dict[FactorId, float]:
    design: dict[FactorId, float] = {}
    for factor_id in item.covers:
        n_a = _ref_neutral_normalized(taxonomy, factor_id, item.profile_a[factor_id])
        n_b = _ref_neutral_normalized(taxonomy, factor_id, item.profile_b[factor_id])
        design[factor_id] = n_a - n_b
    return design


def _ref_pairwise_observation_from_item(
    item: PairwiseItem, choice: ChoiceOption | None, taxonomy: FactorTaxonomy
) -> PairwiseObservation:
    design = _ref_pairwise_design_vector(item, taxonomy)
    if choice is None:
        return PairwiseObservation(design=design, outcome=0.5, weight=0.5)
    outcome = 1.0 if choice is ChoiceOption.A else 0.0
    return PairwiseObservation(design=design, outcome=outcome, weight=1.0)


def _ref_disposition_outcome(item: DispositionItem, choice: ChoiceOption | None) -> float:
    if choice is None:
        return 0.5
    y = 1.0 if choice == item.keyed_option else 0.0
    if item.target in _REF_INVERTED_DISPOSITIONS:
        y = 1.0 - y
    return y


def _ref_disposition_observation_from_item(
    item: DispositionItem, choice: ChoiceOption | None
) -> DispositionObservation:
    outcome = _ref_disposition_outcome(item, choice)
    return DispositionObservation(target=item.target, outcome=outcome)


# --- parity assertions -----------------------------------------------------

_CHOICES: tuple[ChoiceOption | None, ...] = (ChoiceOption.A, ChoiceOption.B, None)


class TestPairwiseAdapterParity:
    def test_design_vector_matches_for_every_item(self) -> None:
        for item in INTERVIEW_BANK.pairwise:
            assert pairwise_design_vector(item, TAXONOMY) == _ref_pairwise_design_vector(
                item, TAXONOMY
            )

    def test_observation_matches_for_every_item_and_choice(self) -> None:
        for item in INTERVIEW_BANK.pairwise:
            for choice in _CHOICES:
                promoted = pairwise_observation_from_item(item, choice, TAXONOMY)
                reference = _ref_pairwise_observation_from_item(item, choice, TAXONOMY)
                assert promoted.model_dump() == reference.model_dump()


class TestDispositionAdapterParity:
    def test_outcome_matches_for_every_item_and_choice(self) -> None:
        for item in INTERVIEW_BANK.disposition:
            for choice in _CHOICES:
                assert disposition_outcome(item, choice) == _ref_disposition_outcome(item, choice)

    def test_observation_matches_for_every_item_and_choice(self) -> None:
        for item in INTERVIEW_BANK.disposition:
            for choice in _CHOICES:
                promoted = disposition_observation_from_item(item, choice)
                reference = _ref_disposition_observation_from_item(item, choice)
                assert promoted.model_dump() == reference.model_dump()
