"""`evidence_sufficiency` (spec §06 §4.1)."""

from __future__ import annotations

import math

import pytest

from mindtrace.domain.ids import FactorId
from mindtrace.engines.confidence.config import DEFAULT_CONFIDENCE_CONFIG
from mindtrace.engines.confidence.evidence import evidence_sufficiency

_WEIGHTS = {FactorId("skill_growth"): 0.6, FactorId("autonomy"): 0.4}
_CONFIG = DEFAULT_CONFIDENCE_CONFIG


def test_no_posterior_data_gives_zero_evidence_sufficiency() -> None:
    """The honest cold-start value: no preference engine has ever run."""
    value, n_bar = evidence_sufficiency(None, _WEIGHTS, coverage=0.8, config=_CONFIG)
    assert value == 0.0
    assert n_bar == 0.0


def test_missing_factor_in_n_eff_map_defaults_to_zero() -> None:
    n_eff = {FactorId("skill_growth"): 10.0}  # "autonomy" absent
    value, n_bar = evidence_sufficiency(n_eff, _WEIGHTS, coverage=1.0, config=_CONFIG)
    assert n_bar == pytest.approx(0.6 * 10.0)
    assert value > 0.0


def test_zero_coverage_gives_zero_regardless_of_n_eff() -> None:
    n_eff = {FactorId("skill_growth"): 100.0, FactorId("autonomy"): 100.0}
    value, _ = evidence_sufficiency(n_eff, _WEIGHTS, coverage=0.0, config=_CONFIG)
    assert value == 0.0


def test_saturates_toward_one_as_n_bar_grows() -> None:
    small = evidence_sufficiency(
        {FactorId("skill_growth"): 1.0, FactorId("autonomy"): 1.0},
        _WEIGHTS,
        coverage=1.0,
        config=_CONFIG,
    )[0]
    large = evidence_sufficiency(
        {FactorId("skill_growth"): 1000.0, FactorId("autonomy"): 1000.0},
        _WEIGHTS,
        coverage=1.0,
        config=_CONFIG,
    )[0]
    assert small < large
    assert large > 0.99


def test_matches_hand_computed_value_at_n_bar_four() -> None:
    # spec §06 §4.1: N_bar = 4 -> saturation ~ 0.63 (1 - e^-1), coverage=1 -> es = 0.63...
    n_eff = {FactorId("skill_growth"): 4.0, FactorId("autonomy"): 4.0}
    value, n_bar = evidence_sufficiency(n_eff, _WEIGHTS, coverage=1.0, config=_CONFIG)
    assert n_bar == pytest.approx(4.0)
    assert value == pytest.approx(1.0 - math.exp(-1.0), abs=1e-9)


def test_partial_coverage_gives_partial_credit_via_sqrt() -> None:
    n_eff = {FactorId("skill_growth"): 100.0, FactorId("autonomy"): 100.0}
    full = evidence_sufficiency(n_eff, _WEIGHTS, coverage=1.0, config=_CONFIG)[0]
    half = evidence_sufficiency(n_eff, _WEIGHTS, coverage=0.25, config=_CONFIG)[0]
    assert half == pytest.approx(full * 0.5, abs=1e-9)
