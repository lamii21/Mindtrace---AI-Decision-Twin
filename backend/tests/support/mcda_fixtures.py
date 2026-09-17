"""The reference twin `T-ref` and the five spec/05 §9 worked examples, as fixtures.

`T_REF_WEIGHTS` is the corrected version of the table in
``docs/spec/05-mcda-mathematics.md`` §9 (the published table's ten listed
values summed to 1.07 before even adding the stated 0.03 residual - a real
bug, fixed by proportionally rescaling those ten values to 0.97; see that
spec's correction note and the M3 final report for the full derivation and
proof that this changes nothing else - contribution percentages, `S`,
`label`, `margin` - only `coverage`'s absolute value).
"""

from __future__ import annotations

from mindtrace.domain.decision import DispositionInputs, FactorReading, FactorVector, WeightVector
from mindtrace.domain.factors import FactorTaxonomy, load_factor_taxonomy
from mindtrace.domain.ids import FactorId

TAXONOMY: FactorTaxonomy = load_factor_taxonomy()

# The ten factors spec/05 s9 names explicitly, before the 0.97-rescale.
_LISTED_RAW_WEIGHTS: dict[str, float] = {
    "skill_growth": 0.22,
    "financial_return": 0.16,
    "downside_risk": 0.14,
    "financial_security": 0.10,
    "location_fit": 0.10,
    "intrinsic_interest": 0.10,
    "autonomy": 0.08,
    "stability": 0.06,
    "social_fit": 0.06,
    "reversibility": 0.05,
}
_RESIDUAL_WEIGHT_EACH = 0.005  # 6 factors x 0.005 = the spec's stated 0.03 residual, unchanged


def _t_ref_weights() -> WeightVector:
    scale = 0.97 / sum(_LISTED_RAW_WEIGHTS.values())
    weights = {FactorId(k): v * scale for k, v in _LISTED_RAW_WEIGHTS.items()}
    for factor_id in TAXONOMY.core_ids:
        weights.setdefault(factor_id, _RESIDUAL_WEIGHT_EACH)
    return WeightVector(weights=weights)


T_REF_WEIGHTS: WeightVector = _t_ref_weights()

T_REF_DISPOSITIONS = DispositionInputs(
    risk_tolerance=0.35, time_discount=0.5, ambiguity_aversion=0.5, effort_tolerance=0.5
)


def factor_vector(known_levels: dict[str, str]) -> FactorVector:
    """Build a `FactorVector` over every core factor: `known_levels` are known, the rest are not."""
    items = []
    for factor_id in TAXONOMY.core_ids:
        level = known_levels.get(factor_id)
        if level is None:
            items.append((FactorId(factor_id), FactorReading(known=False)))
        else:
            items.append((FactorId(factor_id), FactorReading(known=True, level=level)))  # type: ignore[arg-type]
    return FactorVector.from_items(items)


# Example 1 - clear ACCEPT: "Backend internship. Pays 1400 EUR/mo, uses the stack I want to
# learn, established company with a strong completion record, in my city."
EXAMPLE_1_FACTORS = factor_vector(
    {
        "skill_growth": "very_high",
        "financial_return": "high",
        "financial_security": "high",
        "downside_risk": "low",
        "location_fit": "very_high",
        "intrinsic_interest": "high",
    }
)

# Example 2 - clear REJECT: unpaid role, quit current job, company might fold, little learning.
EXAMPLE_2_FACTORS = factor_vector(
    {
        "financial_return": "very_low",
        "financial_security": "very_low",
        "downside_risk": "very_high",
        "location_fit": "very_low",
        "stability": "very_low",
        "skill_growth": "low",
    }
)

# Example 3 - near tie -> UNCERTAIN (score_in_band): better pay/learning, rough commute,
# lukewarm team, moderate risk.
EXAMPLE_3_FACTORS = factor_vector(
    {
        "financial_return": "high",
        "skill_growth": "high",
        "location_fit": "low",
        "social_fit": "low",
        "downside_risk": "moderate",
        "intrinsic_interest": "moderate",
    }
)

# Example 4 - conflicting factors, resolves to ACCEPT at low margin: startup offer, huge
# learning/autonomy/interest, pay cut, real failure risk, but reversible.
EXAMPLE_4_FACTORS = factor_vector(
    {
        "skill_growth": "very_high",
        "autonomy": "very_high",
        "intrinsic_interest": "very_high",
        "financial_return": "low",
        "financial_security": "low",
        "downside_risk": "high",
        "reversibility": "very_high",
    }
)

# Example 5 - insufficient evidence -> UNCERTAIN (insufficient_coverage): only 2/16 factors known.
EXAMPLE_5_FACTORS = factor_vector(
    {
        "intrinsic_interest": "moderate",
        "downside_risk": "moderate",
    }
)
