"""`extraction_entropy` (spec §06 §4.4)."""

from __future__ import annotations

import pytest

from mindtrace.domain.confidence import ExtractionSignal
from mindtrace.domain.ids import FactorId
from mindtrace.engines.confidence.errors import ConfidenceValidationError
from mindtrace.engines.confidence.extraction import extraction_entropy

_WEIGHTS = {FactorId("skill_growth"): 0.6, FactorId("autonomy"): 0.4}


def test_no_signal_is_unavailable_not_the_single_path_default() -> None:
    entropy, path = extraction_entropy(None, _WEIGHTS)
    assert entropy is None
    assert path == "unavailable"


def test_single_path_uses_the_spec_fixed_default() -> None:
    entropy, path = extraction_entropy(ExtractionSignal.single(), _WEIGHTS)
    assert entropy == pytest.approx(0.10)
    assert path == "single"


def test_self_consistency_full_agreement_gives_zero_entropy() -> None:
    signal = ExtractionSignal.self_consistency(
        {FactorId("skill_growth"): 1.0, FactorId("autonomy"): 1.0}
    )
    entropy, path = extraction_entropy(signal, _WEIGHTS)
    assert entropy == pytest.approx(0.0)
    assert path == "self_consistency"


def test_self_consistency_zero_agreement_gives_entropy_one() -> None:
    signal = ExtractionSignal.self_consistency(
        {FactorId("skill_growth"): 0.0, FactorId("autonomy"): 0.0}
    )
    entropy, _ = extraction_entropy(signal, _WEIGHTS)
    assert entropy == pytest.approx(1.0)


def test_self_consistency_weighted_by_decision_weights() -> None:
    signal = ExtractionSignal.self_consistency(
        {FactorId("skill_growth"): 1.0, FactorId("autonomy"): 0.0}
    )
    entropy, _ = extraction_entropy(signal, _WEIGHTS)
    # weighted_agreement = 0.6*1.0 + 0.4*0.0 = 0.6 -> entropy = 0.4
    assert entropy == pytest.approx(0.4)


def test_self_consistency_missing_a_known_factor_raises() -> None:
    signal = ExtractionSignal.self_consistency({FactorId("skill_growth"): 1.0})
    with pytest.raises(ConfidenceValidationError, match="missing="):
        extraction_entropy(signal, _WEIGHTS)


def test_self_consistency_with_an_extra_unknown_factor_raises() -> None:
    signal = ExtractionSignal.self_consistency(
        {
            FactorId("skill_growth"): 1.0,
            FactorId("autonomy"): 1.0,
            FactorId("not_a_known_factor"): 0.5,
        }
    )
    with pytest.raises(ConfidenceValidationError, match="extra="):
        extraction_entropy(signal, _WEIGHTS)
