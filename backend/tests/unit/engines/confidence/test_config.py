"""`ConfidenceConfig`'s own invariants (spec §06 §3)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mindtrace.engines.confidence.config import (
    DEFAULT_CONFIDENCE_CONFIG,
    ConfidenceConfig,
    RecalibrationParams,
)


def test_default_config_weights_sum_to_one() -> None:
    total = (
        DEFAULT_CONFIDENCE_CONFIG.a_evidence
        + DEFAULT_CONFIDENCE_CONFIG.b_ensemble
        + DEFAULT_CONFIDENCE_CONFIG.c_calibration
        + DEFAULT_CONFIDENCE_CONFIG.d_extraction
        + DEFAULT_CONFIDENCE_CONFIG.e_margin
    )
    assert total == pytest.approx(1.0)


def test_default_config_has_no_recalibration() -> None:
    """No prediction ledger exists yet - the default config must not pretend otherwise."""
    assert DEFAULT_CONFIDENCE_CONFIG.recalibration is None


def test_default_config_is_frozen() -> None:
    with pytest.raises(ValidationError):
        DEFAULT_CONFIDENCE_CONFIG.c_min = 0.5


@pytest.mark.parametrize(
    "overrides",
    [
        {"version": "  "},
        {"a_evidence": 0.9},  # breaks the sum-to-1 invariant
        {
            "a_evidence": -0.1,
            "b_ensemble": 0.3,
            "c_calibration": 0.3,
            "d_extraction": 0.3,
            "e_margin": 0.2,
        },
        {"k_eff": 0.0},
        {"k_eff": -1.0},
        {"disagree_norm": 0.0},
        {"label_disagree_penalty": -0.1},
        {"label_disagree_penalty": 1.1},
        {"degenerate_es_cutoff": 1.1},
        {"degenerate_ensemble_cap": -0.1},
        {"n_cal_min": 0},
        {"hc_prior": 1.1},
        {"n_recal": 0},
        {"c_min": -0.01},
    ],
)
def test_invalid_overrides_are_rejected(overrides: dict[str, float | str]) -> None:
    with pytest.raises(ValidationError):
        ConfidenceConfig(**overrides)  # type: ignore[arg-type]


def test_weights_summing_to_one_via_a_different_split_is_accepted() -> None:
    config = ConfidenceConfig(
        a_evidence=0.5, b_ensemble=0.2, c_calibration=0.1, d_extraction=0.1, e_margin=0.1
    )
    assert config.a_evidence == 0.5


def test_recalibration_params_can_be_attached() -> None:
    config = ConfidenceConfig(recalibration=RecalibrationParams(alpha=0.1, beta=1.2))
    assert config.recalibration is not None
    assert config.recalibration.alpha == 0.1
