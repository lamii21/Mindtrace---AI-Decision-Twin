"""The production interview-answer -> preference-observation adapter (M8; spec/07 §4).

Promoted from the test-only adapter ``tests/support/preference_fixtures.py``
has used since M4/M6-A's own tests (identical logic - that module now
re-exports from here rather than keeping a second implementation). Converts
one interview answer (a :class:`~mindtrace.domain.interview.PairwiseItem`/
:class:`~mindtrace.domain.interview.DispositionItem` plus the user's choice)
into the Bradley-Terry/Beta observation types
:mod:`mindtrace.engines.preference.update` already consumes - computes no
posterior itself, and reuses MCDA's own :func:`~mindtrace.engines.mcda.
normalize.normalize_factor` for the design vector (spec/07 §4.1's explicit
instruction to use the neutral-disposition curve, ``gamma = 1``, so the
interview prior does not depend on dispositions it is simultaneously
estimating). No Bradley-Terry or Beta mathematics is duplicated here.
"""

from __future__ import annotations

from mindtrace.domain.decision import DispositionInputs
from mindtrace.domain.enums import ChoiceOption, ScaleLevel
from mindtrace.domain.factors import FactorTaxonomy
from mindtrace.domain.ids import DispositionId, FactorId
from mindtrace.domain.interview import DispositionItem, PairwiseItem
from mindtrace.domain.traits import DispositionObservation, PairwiseObservation
from mindtrace.engines.mcda.config import DEFAULT_MCDA_CONFIG, MCDAConfig
from mindtrace.engines.mcda.normalize import normalize_factor

_NEUTRAL = DispositionInputs.neutral()

# Dispositions whose Beta posterior moves *opposite* the keyed-option choice
# (spec/07 §4.2's table): choosing the "patient"/"ambiguity-tolerant" side
# raises patience/tolerance, which is a LOW `time_discount`/
# `ambiguity_aversion` value - the one sign-inversion spec/07 requires.
# Matches `mindtrace.domain.interview`'s own `_KEYED_FIELDS` mapping
# (`patient_option` -> INTERTEMPORAL, `ambiguity_seeking_option` -> AMBIGUITY).
INVERTED_DISPOSITIONS: frozenset[DispositionId] = frozenset(
    {DispositionId("time_discount"), DispositionId("ambiguity_aversion")}
)


def _neutral_normalized(
    taxonomy: FactorTaxonomy, factor_id: FactorId, level: ScaleLevel, config: MCDAConfig
) -> float:
    spec = taxonomy.get(factor_id)
    anchor = spec.anchor_for(level)
    return normalize_factor(spec, anchor, _NEUTRAL, config)


def pairwise_design_vector(
    item: PairwiseItem, taxonomy: FactorTaxonomy, *, config: MCDAConfig = DEFAULT_MCDA_CONFIG
) -> dict[FactorId, float]:
    """`x_{k,i} = n_i(A_k) - n_i(B_k)` over `item.covers` (spec/07 §4.1).

    Uses the neutral-disposition curve (`gamma = 1`) via MCDA's own
    `normalize_factor` - no normalisation math is reimplemented here.
    """
    design: dict[FactorId, float] = {}
    for factor_id in item.covers:
        n_a = _neutral_normalized(taxonomy, factor_id, item.profile_a[factor_id], config)
        n_b = _neutral_normalized(taxonomy, factor_id, item.profile_b[factor_id], config)
        design[factor_id] = n_a - n_b
    return design


def pairwise_observation_from_item(
    item: PairwiseItem,
    choice: ChoiceOption | None,
    taxonomy: FactorTaxonomy,
    *,
    config: MCDAConfig = DEFAULT_MCDA_CONFIG,
) -> PairwiseObservation:
    """`choice=None` means "indifferent": `outcome=0.5`, `weight=0.5` (spec/07 §4.1)."""
    design = pairwise_design_vector(item, taxonomy, config=config)
    if choice is None:
        return PairwiseObservation(design=design, outcome=0.5, weight=0.5)
    outcome = 1.0 if choice is ChoiceOption.A else 0.0
    return PairwiseObservation(design=design, outcome=outcome, weight=1.0)


def disposition_outcome(item: DispositionItem, choice: ChoiceOption | None) -> float:
    """`y_eff`, including the `time_discount`/`ambiguity_aversion` inversion (spec/07 §4.2)."""
    if choice is None:
        return 0.5
    y = 1.0 if choice == item.keyed_option else 0.0
    if item.target in INVERTED_DISPOSITIONS:
        y = 1.0 - y
    return y


def disposition_observation_from_item(
    item: DispositionItem, choice: ChoiceOption | None
) -> DispositionObservation:
    """The effective Beta-update observation for one disposition answer (spec/07 §4.2)."""
    return DispositionObservation(target=item.target, outcome=disposition_outcome(item, choice))


__all__ = [
    "INVERTED_DISPOSITIONS",
    "disposition_observation_from_item",
    "disposition_outcome",
    "pairwise_design_vector",
    "pairwise_observation_from_item",
]
