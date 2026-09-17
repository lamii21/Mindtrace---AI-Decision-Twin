"""Reusable confidence-engine fixtures built on top of `tests.support.mcda_fixtures`.

Spec §06 has no hand-worked numeric examples the way spec §05 §9 does, so
these are **implementation fixtures**: transparent, hand-traceable inputs
built strictly from the documented formula, not empirical evidence of a real
user's calibration or a real ensemble's disagreement.
"""

from __future__ import annotations

from mindtrace.domain.confidence import (
    CalibrationLedger,
    CalibrationRecord,
    EnsembleObservation,
    ExtractionSignal,
)
from mindtrace.domain.decision import DecisionResult, FactorVector
from mindtrace.domain.enums import DecisionOutcome
from mindtrace.domain.ids import FactorId
from mindtrace.engines.mcda.decide import decide
from tests.support.mcda_fixtures import (
    EXAMPLE_1_FACTORS,
    EXAMPLE_2_FACTORS,
    EXAMPLE_3_FACTORS,
    EXAMPLE_4_FACTORS,
    EXAMPLE_5_FACTORS,
    T_REF_DISPOSITIONS,
    T_REF_WEIGHTS,
    TAXONOMY,
)


def decide_example(factors: FactorVector) -> DecisionResult:
    return decide(TAXONOMY, T_REF_WEIGHTS, factors, T_REF_DISPOSITIONS)


DECISION_EXAMPLE_1 = decide_example(EXAMPLE_1_FACTORS)
DECISION_EXAMPLE_2 = decide_example(EXAMPLE_2_FACTORS)
DECISION_EXAMPLE_3 = decide_example(EXAMPLE_3_FACTORS)
DECISION_EXAMPLE_4 = decide_example(EXAMPLE_4_FACTORS)
DECISION_EXAMPLE_5 = decide_example(EXAMPLE_5_FACTORS)

# A generous per-factor effective-sample-size map: every factor the T-ref
# examples ever use as `known`, given plenty of (hypothetical) posterior
# evidence - lets tests exercise `evidence_sufficiency` away from its
# cold-start floor without pretending a real preference engine ran.
GENEROUS_N_EFF: dict[FactorId, float] = {
    FactorId(fid): 12.0
    for fid in (
        "skill_growth",
        "financial_return",
        "financial_security",
        "downside_risk",
        "location_fit",
        "intrinsic_interest",
        "stability",
        "autonomy",
        "reversibility",
    )
}

_A = DecisionOutcome.ACCEPT
_R = DecisionOutcome.REJECT
_U = DecisionOutcome.UNCERTAIN

UNANIMOUS_ENSEMBLE = EnsembleObservation(
    scores=(0.69, 0.70, 0.68, 0.71, 0.69),
    labels=(_A, _A, _A, _A, _A),
)

DISAGREEING_ENSEMBLE = EnsembleObservation(
    scores=(0.69, -0.40, 0.55, 0.10, -0.20),
    labels=(_A, _R, _A, _U, _R),
)

WELL_CALIBRATED_LEDGER = CalibrationLedger(
    domain_records=tuple(
        CalibrationRecord(predicted_confidence=c, correct=correct)
        for c, correct in [
            (0.9, True),
            (0.9, True),
            (0.9, True),
            (0.85, True),
            (0.7, True),
            (0.7, False),
            (0.7, True),
            (0.5, True),
            (0.5, False),
            (0.3, False),
            (0.3, True),
            (0.1, False),
        ]
    )
)

POORLY_CALIBRATED_LEDGER = CalibrationLedger(
    domain_records=tuple(
        CalibrationRecord(predicted_confidence=c, correct=correct)
        for c, correct in [
            (0.9, False),
            (0.9, False),
            (0.9, True),
            (0.85, False),
            (0.7, False),
            (0.7, False),
            (0.7, True),
            (0.5, False),
            (0.5, False),
            (0.3, True),
            (0.3, True),
            (0.1, True),
        ]
    )
)


def self_consistency_signal(agreement_value: float, decision: DecisionResult) -> ExtractionSignal:
    """A `self_consistency` signal giving every known factor the same agreement score."""
    agreement = {FactorId(c.factor_id): agreement_value for c in decision.contributions}
    return ExtractionSignal.self_consistency(agreement)
