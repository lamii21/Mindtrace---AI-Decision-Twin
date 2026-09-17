"""Reusable preference-engine fixtures, incl. an interview-item-bank adapter.

That adapter (`pairwise_observation_from_item`/`disposition_outcome`) computing
Bradley-Terry design vectors from a real `PairwiseItem`/`DispositionItem` is
**test-only**: `mindtrace.domain.interview`'s own module docstring reserves
that conversion for milestone M8's elicitation session, and
`mindtrace.engines.preference` never imports `mindtrace.domain.interview` in
production code. It exists here only so the spec/07 §7 "recovery" test and
the "all 24 interview answers" golden scenario can be built against the real
item bank instead of a hand-rolled substitute.
"""

from __future__ import annotations

from mindtrace.domain.decision import DispositionInputs
from mindtrace.domain.enums import ChoiceOption
from mindtrace.domain.factors import FactorTaxonomy, load_factor_taxonomy
from mindtrace.domain.ids import DispositionId, FactorId
from mindtrace.domain.interview import (
    DispositionItem,
    InterviewBank,
    PairwiseItem,
    load_interview_bank,
)
from mindtrace.domain.traits import (
    DispositionObservation,
    PairwiseObservation,
    TraitModel,
    load_trait_model,
)
from mindtrace.engines.mcda.config import DEFAULT_MCDA_CONFIG
from mindtrace.engines.mcda.normalize import normalize_factor

TAXONOMY: FactorTaxonomy = load_factor_taxonomy()
TRAIT_MODEL: TraitModel = load_trait_model(taxonomy=TAXONOMY)
INTERVIEW_BANK: InterviewBank = load_interview_bank(taxonomy=TAXONOMY, trait_model=TRAIT_MODEL)

_NEUTRAL = DispositionInputs.neutral()
_INVERTED_DISPOSITIONS = frozenset(
    {DispositionId("time_discount"), DispositionId("ambiguity_aversion")}
)


def _neutral_normalized(factor_id: FactorId, level: object) -> float:
    spec = TAXONOMY.get(factor_id)
    anchor = spec.anchor_for(level)  # type: ignore[arg-type]
    return normalize_factor(spec, anchor, _NEUTRAL, DEFAULT_MCDA_CONFIG)


def pairwise_design_vector(item: PairwiseItem) -> dict[FactorId, float]:
    """`x_{k,i} = n_i(A_k) - n_i(B_k)` over `item.covers` (spec/07 §4.1).

    Uses the neutral-disposition curve (`gamma = 1`, spec/07 §4.1: "so the
    prior does not depend on dispositions that are themselves being
    estimated") via M3's own `normalize_factor` - no normalisation math is
    reimplemented here.
    """
    design: dict[FactorId, float] = {}
    for factor_id in item.covers:
        n_a = _neutral_normalized(factor_id, item.profile_a[factor_id])
        n_b = _neutral_normalized(factor_id, item.profile_b[factor_id])
        design[factor_id] = n_a - n_b
    return design


def pairwise_observation_from_item(
    item: PairwiseItem, choice: ChoiceOption | None
) -> PairwiseObservation:
    """`choice=None` means "indifferent": `outcome=0.5`, `weight=0.5` (spec/07 §4.1)."""
    if choice is None:
        return PairwiseObservation(design=pairwise_design_vector(item), outcome=0.5, weight=0.5)
    outcome = 1.0 if choice is ChoiceOption.A else 0.0
    return PairwiseObservation(design=pairwise_design_vector(item), outcome=outcome, weight=1.0)


def disposition_outcome(item: DispositionItem, choice: ChoiceOption | None) -> float:
    """`y_eff`, including the `time_discount`/`ambiguity_aversion` inversion (spec/07 §4.2)."""
    if choice is None:
        return 0.5
    y = 1.0 if choice == item.keyed_option else 0.0
    if item.target in _INVERTED_DISPOSITIONS:
        y = 1.0 - y
    return y


def disposition_observation_from_item(
    item: DispositionItem, choice: ChoiceOption | None
) -> DispositionObservation:
    return DispositionObservation(target=item.target, outcome=disposition_outcome(item, choice))


def all_pairwise_observations(choose: ChoiceOption = ChoiceOption.A) -> list[PairwiseObservation]:
    """Every pairwise item in the bank, all answered the same fixed way.

    A simple, fully-deterministic synthetic respondent for golden/property fixtures.
    """
    return [pairwise_observation_from_item(item, choose) for item in INTERVIEW_BANK.pairwise]


def all_disposition_observations(
    choose: ChoiceOption = ChoiceOption.A,
) -> list[DispositionObservation]:
    return [disposition_observation_from_item(item, choose) for item in INTERVIEW_BANK.disposition]
