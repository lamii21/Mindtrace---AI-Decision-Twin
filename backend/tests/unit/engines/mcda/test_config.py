"""`MCDAConfig`'s own invariants (spec/05 s0): every constant range, and the
tau_reject == -tau_accept symmetry the spec calls out by name.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mindtrace.engines.mcda.config import DEFAULT_MCDA_CONFIG, MCDAConfig


def test_default_config_is_valid() -> None:
    assert DEFAULT_MCDA_CONFIG.tau_reject == -DEFAULT_MCDA_CONFIG.tau_accept


def test_default_config_is_frozen() -> None:
    with pytest.raises(ValidationError):
        DEFAULT_MCDA_CONFIG.tau_accept = 0.5  # type: ignore[misc]


@pytest.mark.parametrize(
    "overrides",
    [
        {"version": "  "},
        {"tau_accept": 0.0},
        {"tau_accept": -0.1},
        {"tau_reject": -0.19, "tau_accept": 0.20},
        {"coverage_min": -0.01},
        {"coverage_min": 1.01},
        {"ambiguity_coverage_slope": -0.01},
        {"ambiguity_coverage_slope": 1.01},
        {"margin_ref": 0.0},
        {"score_scale": 0.0},
        {"score_scale": -1.0},
        {"baseline_n": -0.01},
        {"baseline_n": 1.01},
        {"k_risk": 0.0},
        {"k_effort": 0.0},
    ],
)
def test_invalid_overrides_are_rejected(overrides: dict[str, float | str]) -> None:
    with pytest.raises(ValidationError):
        MCDAConfig(**overrides)  # type: ignore[arg-type]


def test_symmetric_tau_override_is_accepted() -> None:
    config = MCDAConfig(tau_accept=0.3, tau_reject=-0.3)
    assert config.tau_accept == 0.3
    assert config.tau_reject == -0.3
