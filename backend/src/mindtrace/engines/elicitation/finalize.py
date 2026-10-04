"""Finalising a completed Twin Interview into a ``PreferencePosterior`` (spec/07 §4.3).

Pure: takes the full answer log (already deduplicated to one answer per item
by ``events.projectors.preference.fold_elicitation_answers``) and produces a
``(posterior, interview_noise)`` pair. Calls M4's existing batch-update
functions exactly once each - never incrementally, per spec/04 §3's explicit
"Laplace error accumulates" warning - and computes no Bradley-Terry or Beta
mathematics of its own.
"""

from __future__ import annotations

from mindtrace.domain.enums import ChoiceOption
from mindtrace.domain.factors import FactorTaxonomy
from mindtrace.domain.ids import InterviewItemId
from mindtrace.domain.interview import InterviewBank
from mindtrace.domain.traits import PreferencePosterior
from mindtrace.engines.preference.config import PreferenceConfig
from mindtrace.engines.preference.interview import (
    disposition_observation_from_item,
    pairwise_observation_from_item,
)
from mindtrace.engines.preference.update import (
    apply_disposition_observations,
    apply_pairwise_observations,
)

FINALIZE_VERSION = "1"

_CONSISTENCY_TOLERANCE = 1e-9


def consistency_pairs(bank: InterviewBank) -> tuple[tuple[InterviewItemId, InterviewItemId], ...]:
    """``(original_id, repeat_id)`` pairs, derived from ``consistency_check_item_ids``.

    By the repository's own naming convention (the repeat id minus its
    trailing ``"r"``) - verified against ``schema/interview.yaml``: each
    repeat's A/B profiles are its original's exact swap, so this pairing is
    not an invented rule, it is read straight off the data.
    """
    pairs: list[tuple[InterviewItemId, InterviewItemId]] = []
    for repeat_id in bank.config.consistency_check_item_ids:
        original_id = InterviewItemId(str(repeat_id)[:-1])
        pairs.append((original_id, repeat_id))
    return tuple(pairs)


def _choice_to_y(choice: ChoiceOption | None) -> float:
    """The "chose A" indicator: 1.0/0.0/0.5 for A/B/indifferent (spec/07 §4.1)."""
    if choice is None:
        return 0.5
    return 1.0 if choice is ChoiceOption.A else 0.0


def compute_interview_noise(
    bank: InterviewBank, answers: dict[InterviewItemId, ChoiceOption | None]
) -> float:
    """``disagreement_count / total_consistency_pairs`` (M8 planning s23, approved formula).

    A consistent respondent's "chose A" indicator on a consistency-check
    repeat is the complement of their indicator on the original - the
    repeat's design vector is the original's exact negation (see
    :func:`consistency_pairs`'s docstring), so ``y_original + y_repeat == 1``
    for a perfectly consistent answer pair. A pair the user never answered
    (should not occur once the fixed order is complete) is simply excluded
    from the denominator rather than counted as a disagreement.
    """
    pairs = consistency_pairs(bank)
    if not pairs:
        return 0.0
    disagreements = 0
    counted = 0
    for original_id, repeat_id in pairs:
        if original_id not in answers or repeat_id not in answers:
            continue
        counted += 1
        y_original = _choice_to_y(answers[original_id])
        y_repeat = _choice_to_y(answers[repeat_id])
        if abs((y_original + y_repeat) - 1.0) > _CONSISTENCY_TOLERANCE:
            disagreements += 1
    if counted == 0:
        return 0.0
    return disagreements / counted


def finalize_interview(
    bank: InterviewBank,
    taxonomy: FactorTaxonomy,
    prior: PreferencePosterior,
    answers: dict[InterviewItemId, ChoiceOption | None],
    *,
    base_config: PreferenceConfig,
) -> tuple[PreferencePosterior, float]:
    """Run the one consolidated batch update over every answered item (spec/07 §4.1/§4.3).

    Returns ``(posterior, interview_noise)``. ``base_config.logistic_scale_s``
    is inflated by ``(1 + interview_noise)`` for this one pass only
    (``s_user = s * (1 + interview_noise)``, spec/07 §4.1) - every other
    constant (``newton_steps``, ``pseudocount_kappa``, ...) is the caller's
    unmodified ``PreferenceConfig``. This is a *measurement-quality* signal,
    never an ordinary Bradley-Terry observation: it only ever scales the
    shared likelihood-noise parameter for this pass, and the consistency-pair
    answers themselves still enter the batch as regular pairwise observations
    like any other answered item (spec/07 §3.7/§4.1 - interview noise and
    preference evidence stay conceptually and mechanically separate; nothing
    here fabricates a preference direction from a disagreement).
    """
    interview_noise = compute_interview_noise(bank, answers)
    config = base_config.model_copy(
        update={"logistic_scale_s": base_config.logistic_scale_s * (1.0 + interview_noise)}
    )

    pairwise_by_id = {item.id: item for item in bank.pairwise}
    disposition_by_id = {item.id: item for item in bank.disposition}

    pairwise_observations = [
        pairwise_observation_from_item(pairwise_by_id[item_id], choice, taxonomy)
        for item_id, choice in answers.items()
        if item_id in pairwise_by_id
    ]
    disposition_observations = [
        disposition_observation_from_item(disposition_by_id[item_id], choice)
        for item_id, choice in answers.items()
        if item_id in disposition_by_id
    ]

    posterior = apply_pairwise_observations(prior, pairwise_observations, config)
    posterior = apply_disposition_observations(posterior, disposition_observations, config)
    return posterior, interview_noise


__all__ = [
    "FINALIZE_VERSION",
    "compute_interview_noise",
    "consistency_pairs",
    "finalize_interview",
]
