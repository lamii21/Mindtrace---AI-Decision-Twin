"""A minimal, valid ``TwinConfigResult`` builder for M10 ensemble/debate unit tests.

Fills in every field a real ``decide()`` call would produce with small,
fixed defaults - only ``twin``/``contributions``/``score``/``label`` are
ever varied by a caller, since those are the only fields
``engines.debate``'s diagnostics actually read.
"""

from __future__ import annotations

from collections.abc import Mapping

from mindtrace.domain.decision import Contribution, DecisionResult, DispositionInputs, WeightVector
from mindtrace.domain.enums import DecisionOutcome, ScaleLevel
from mindtrace.domain.ids import FactorId
from mindtrace.domain.simulation import TwinConfigResult
from mindtrace.domain.traits import EffectiveWeightVector
from mindtrace.engines.preference.config import ENGINE_VERSION, PROJECTION_VERSION
from tests.support.preference_fixtures import TRAIT_MODEL

_NEUTRAL_DISPOSITIONS = DispositionInputs.neutral()


def _effective_weight_vector() -> EffectiveWeightVector:
    ids = list(TRAIT_MODEL.core_weight_factor_ids)
    return EffectiveWeightVector(
        weights=WeightVector(weights=dict.fromkeys(ids, 1.0 / len(ids))),
        dispositions=_NEUTRAL_DISPOSITIONS,
        trait_schema_version=TRAIT_MODEL.version,
        preference_engine_version=ENGINE_VERSION,
        projection_version=PROJECTION_VERSION,
        read_transform="softmax",
        total_weight_evidence_count=0,
        total_disposition_evidence_count=0,
    )


def twin_result_with(
    *,
    twin: str,
    contributions: Mapping[str, float],
    score: float = 0.0,
    label: DecisionOutcome = DecisionOutcome.ACCEPT,
) -> TwinConfigResult:
    """A ``TwinConfigResult`` named ``twin`` whose contributions are exactly ``contributions``.

    Every ``Contribution`` gets the same placeholder ``level_a``/``weight``/
    ``normalized_value_a``/``normalized_value_b``/``contribution_pct`` - only
    ``factor_id``/``raw_contribution`` vary, since that is all
    ``engines.debate.disagreement.conflict_axis`` reads.
    """
    contribution_objs = tuple(
        Contribution(
            factor_id=FactorId(factor_id),
            level_a=ScaleLevel.HIGH,
            weight=1.0,
            normalized_value_a=1.0,
            normalized_value_b=0.0,
            raw_contribution=raw_contribution,
            contribution_pct=0.0,
        )
        for factor_id, raw_contribution in contributions.items()
    )
    decision = DecisionResult(
        engine_version=ENGINE_VERSION,
        config_version="1",
        score=score,
        raw_score=score,
        raw_label=label,
        label=label,
        uncertain_reason=None,
        coverage=1.0,
        margin=0.1,
        known_factor_count=len(contribution_objs),
        total_factor_count=len(contribution_objs),
        contributions=contribution_objs,
    )
    return TwinConfigResult(twin=twin, preference=_effective_weight_vector(), decision=decision)


__all__ = ["twin_result_with"]
