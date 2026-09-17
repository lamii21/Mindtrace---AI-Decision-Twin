"""`margin_adequacy` (spec §06 §4.5)."""

from __future__ import annotations

import pytest

from mindtrace.engines.confidence.margin import margin_adequacy
from mindtrace.engines.mcda.config import DEFAULT_MCDA_CONFIG


def test_negative_margin_clamps_to_zero() -> None:
    assert margin_adequacy(-0.3, DEFAULT_MCDA_CONFIG) == 0.0


def test_margin_at_reference_gives_one() -> None:
    result = margin_adequacy(DEFAULT_MCDA_CONFIG.margin_ref, DEFAULT_MCDA_CONFIG)
    assert result == pytest.approx(1.0)


def test_margin_beyond_reference_clamps_to_one() -> None:
    assert margin_adequacy(10.0, DEFAULT_MCDA_CONFIG) == 1.0


def test_margin_halfway_to_reference_gives_half() -> None:
    half_margin = DEFAULT_MCDA_CONFIG.margin_ref / 2.0
    assert margin_adequacy(half_margin, DEFAULT_MCDA_CONFIG) == pytest.approx(0.5)


def test_zero_margin_gives_zero() -> None:
    assert margin_adequacy(0.0, DEFAULT_MCDA_CONFIG) == 0.0
