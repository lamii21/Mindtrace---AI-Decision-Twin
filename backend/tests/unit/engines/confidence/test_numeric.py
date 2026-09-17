"""`_numeric.py`'s small shared helpers."""

from __future__ import annotations

import math

import pytest

from mindtrace.engines.confidence._numeric import clamp, stable_sigmoid


def test_clamp_passes_through_in_range_values() -> None:
    assert clamp(0.5, 0.0, 1.0) == 0.5


def test_clamp_caps_above_high() -> None:
    assert clamp(5.0, 0.0, 1.0) == 1.0


def test_clamp_floors_below_low() -> None:
    assert clamp(-5.0, 0.0, 1.0) == 0.0


def test_stable_sigmoid_at_zero_is_one_half() -> None:
    assert stable_sigmoid(0.0) == pytest.approx(0.5)


def test_stable_sigmoid_matches_naive_formula_for_moderate_x() -> None:
    for x in (-5.0, -1.0, 0.3, 2.0, 5.0):
        assert stable_sigmoid(x) == pytest.approx(1.0 / (1.0 + math.exp(-x)), abs=1e-12)


def test_stable_sigmoid_does_not_overflow_for_large_negative_x() -> None:
    assert stable_sigmoid(-1000.0) == pytest.approx(0.0, abs=1e-12)


def test_stable_sigmoid_does_not_overflow_for_large_positive_x() -> None:
    assert stable_sigmoid(1000.0) == pytest.approx(1.0, abs=1e-12)


def test_stable_sigmoid_stays_in_unit_interval() -> None:
    for x in (-1e6, -100.0, 0.0, 100.0, 1e6):
        value = stable_sigmoid(x)
        assert 0.0 <= value <= 1.0
