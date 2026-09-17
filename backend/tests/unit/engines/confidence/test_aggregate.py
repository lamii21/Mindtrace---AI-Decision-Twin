"""`combine_terms`: omission, renormalization, and clamping (spec §06 §5)."""

from __future__ import annotations

import pytest

from mindtrace.engines.confidence.aggregate import combine_terms
from mindtrace.engines.confidence.config import DEFAULT_CONFIDENCE_CONFIG

_CONFIG = DEFAULT_CONFIDENCE_CONFIG


def test_all_terms_present_uses_the_configured_weights_unmodified() -> None:
    raw_c, weights_used = combine_terms(
        evidence_sufficiency=1.0,
        ensemble_term=1.0,
        historical_calibration=1.0,
        extraction_term=1.0,
        margin_adequacy=1.0,
        config=_CONFIG,
    )
    assert raw_c == pytest.approx(1.0)
    assert weights_used == pytest.approx(
        {
            "A": _CONFIG.a_evidence,
            "B": _CONFIG.b_ensemble,
            "C": _CONFIG.c_calibration,
            "D": _CONFIG.d_extraction,
            "E": _CONFIG.e_margin,
        }
    )


def test_all_terms_zero_gives_raw_c_zero() -> None:
    raw_c, _ = combine_terms(
        evidence_sufficiency=0.0,
        ensemble_term=0.0,
        historical_calibration=0.0,
        extraction_term=0.0,
        margin_adequacy=0.0,
        config=_CONFIG,
    )
    assert raw_c == 0.0


def test_omitted_terms_are_dropped_and_remaining_weights_renormalize() -> None:
    raw_c, weights_used = combine_terms(
        evidence_sufficiency=1.0,
        ensemble_term=None,
        historical_calibration=None,
        extraction_term=None,
        margin_adequacy=1.0,
        config=_CONFIG,
    )
    assert set(weights_used) == {"A", "E"}
    assert sum(weights_used.values()) == pytest.approx(1.0)
    assert raw_c == pytest.approx(1.0)  # both surviving terms are 1.0


def test_renormalized_weights_keep_their_relative_ratio() -> None:
    _, weights_used = combine_terms(
        evidence_sufficiency=0.5,
        ensemble_term=None,
        historical_calibration=0.5,
        extraction_term=None,
        margin_adequacy=0.5,
        config=_CONFIG,
    )
    # A : C : E ratio must equal a_evidence : c_calibration : e_margin
    assert weights_used["A"] / weights_used["C"] == pytest.approx(
        _CONFIG.a_evidence / _CONFIG.c_calibration
    )
    assert weights_used["A"] / weights_used["E"] == pytest.approx(
        _CONFIG.a_evidence / _CONFIG.e_margin
    )


def test_only_evidence_and_margin_present_is_the_current_cold_start_case() -> None:
    raw_c, weights_used = combine_terms(
        evidence_sufficiency=0.2,
        ensemble_term=None,
        historical_calibration=None,
        extraction_term=None,
        margin_adequacy=0.8,
        config=_CONFIG,
    )
    assert set(weights_used) == {"A", "E"}
    expected = (_CONFIG.a_evidence * 0.2 + _CONFIG.e_margin * 0.8) / (
        _CONFIG.a_evidence + _CONFIG.e_margin
    )
    assert raw_c == pytest.approx(expected)


def test_raw_c_is_clamped_to_unit_interval() -> None:
    # Combination of in-range weighted terms can never actually exceed [0, 1]
    # (a convex combination of [0,1] values), but the clamp is still asserted
    # as an explicit safety net per spec §06 §5's own "raw_C = clamp(...)" step.
    raw_c, _ = combine_terms(
        evidence_sufficiency=1.0,
        ensemble_term=1.0,
        historical_calibration=1.0,
        extraction_term=1.0,
        margin_adequacy=1.0,
        config=_CONFIG,
    )
    assert 0.0 <= raw_c <= 1.0
