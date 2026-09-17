"""`historical_calibration` (spec §06 §4.3): the small-`n` omission and Bayesian shrink."""

from __future__ import annotations

import pytest

from mindtrace.domain.confidence import CalibrationLedger, CalibrationRecord
from mindtrace.engines.confidence.calibration import historical_calibration
from mindtrace.engines.confidence.config import DEFAULT_CONFIDENCE_CONFIG

_CONFIG = DEFAULT_CONFIDENCE_CONFIG


def _records(n: int, *, correct: bool, confidence: float = 0.7) -> tuple[CalibrationRecord, ...]:
    return tuple(
        CalibrationRecord(predicted_confidence=confidence, correct=correct) for _ in range(n)
    )


def test_no_ledger_omits_the_term() -> None:
    value, status, n = historical_calibration(None, _CONFIG)
    assert value is None
    assert status == "false"
    assert n == 0


def test_below_both_thresholds_omits_the_term() -> None:
    ledger = CalibrationLedger(
        domain_records=_records(3, correct=True),
        all_domain_records=_records(5, correct=True),
    )
    value, status, n = historical_calibration(ledger, _CONFIG)
    assert value is None
    assert status == "false"
    assert n == 0


def test_domain_records_at_the_minimum_are_used_directly() -> None:
    records = _records(_CONFIG.n_cal_min, correct=True, confidence=0.9)
    ledger = CalibrationLedger(domain_records=records)
    value, status, n = historical_calibration(ledger, _CONFIG)
    assert status == "true"
    assert n == _CONFIG.n_cal_min
    assert value is not None


def test_cross_domain_fallback_when_domain_is_thin_but_all_domain_is_not() -> None:
    ledger = CalibrationLedger(
        domain_records=_records(2, correct=True),
        all_domain_records=_records(_CONFIG.n_cal_min, correct=True, confidence=0.9),
    )
    value, status, n = historical_calibration(ledger, _CONFIG)
    assert status == "cross_domain"
    assert n == _CONFIG.n_cal_min
    assert value is not None


def test_perfectly_calibrated_records_give_ece_zero() -> None:
    # predicted_confidence == accuracy exactly within each bin -> ECE = 0 -> raw = 1.
    # Use a single bin (all same predicted_confidence) with exactly that fraction correct.
    n = 20
    correct_count = 14  # 0.7 accuracy matches predicted_confidence 0.7 exactly
    records = _records(correct_count, correct=True, confidence=0.7) + _records(
        n - correct_count, correct=False, confidence=0.7
    )
    ledger = CalibrationLedger(domain_records=records)
    value, _, n_used = historical_calibration(ledger, _CONFIG)
    assert n_used == n
    raw = correct_count / n
    assert raw == pytest.approx(0.7)
    expected = (n * 1.0 + _CONFIG.n_cal_min * _CONFIG.hc_prior) / (n + _CONFIG.n_cal_min)
    assert value == pytest.approx(expected, abs=1e-9)


def test_shrinks_toward_prior_at_the_minimum_sample_size() -> None:
    # n == N_CAL_MIN -> shrunk value is exactly halfway between raw and HC_PRIOR.
    records = _records(_CONFIG.n_cal_min, correct=True, confidence=1.0)
    ledger = CalibrationLedger(domain_records=records)
    value, _, n = historical_calibration(ledger, _CONFIG)
    assert n == _CONFIG.n_cal_min
    raw = 1.0  # perfectly calibrated: predicted 1.0, 100% correct
    expected = (raw + _CONFIG.hc_prior) / 2.0
    assert value == pytest.approx(expected, abs=1e-9)


def test_large_n_approaches_raw_not_prior() -> None:
    # predicted 0.8, always correct -> accuracy 1.0, ECE = |1.0 - 0.8| = 0.2, raw = 0.8.
    n = 10_000
    records = _records(n, correct=True, confidence=0.8)
    ledger = CalibrationLedger(domain_records=records)
    value, _, n_used = historical_calibration(ledger, _CONFIG)
    assert n_used == n
    assert value is not None
    assert value == pytest.approx(0.8, abs=1e-3)
