"""Combination: drop omitted terms, renormalise the rest, clamp (spec §06 §5).

`evidence_sufficiency` and `margin_adequacy` are never `None` (see
``evidence.py`` and ``margin.py``), so at least weights `A` and `E` always
survive renormalisation - the combination can never divide by zero.
"""

from __future__ import annotations

from mindtrace.engines.confidence._numeric import clamp
from mindtrace.engines.confidence.config import ConfidenceConfig


def combine_terms(
    *,
    evidence_sufficiency: float,
    ensemble_term: float | None,
    historical_calibration: float | None,
    extraction_term: float | None,
    margin_adequacy: float,
    config: ConfidenceConfig,
) -> tuple[float, dict[str, float]]:
    """`(raw_C, weights_used)` - `weights_used` holds only the letters that survived."""
    raw_terms: dict[str, tuple[float, float | None]] = {
        "A": (config.a_evidence, evidence_sufficiency),
        "B": (config.b_ensemble, ensemble_term),
        "C": (config.c_calibration, historical_calibration),
        "D": (config.d_extraction, extraction_term),
        "E": (config.e_margin, margin_adequacy),
    }
    present: dict[str, tuple[float, float]] = {}
    for letter, (weight, value) in raw_terms.items():
        if value is not None:
            present[letter] = (weight, value)

    total_weight = sum(weight for weight, _ in present.values())
    weights_used = {letter: weight / total_weight for letter, (weight, _) in present.items()}
    raw_c = sum(weights_used[letter] * value for letter, (_, value) in present.items())
    return clamp(raw_c, 0.0, 1.0), weights_used
