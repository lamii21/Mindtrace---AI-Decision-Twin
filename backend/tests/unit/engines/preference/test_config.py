"""`PreferenceConfig`'s own invariants."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mindtrace.engines.preference.config import DEFAULT_PREFERENCE_CONFIG, PreferenceConfig


def test_default_config_matches_spec_constants() -> None:
    assert DEFAULT_PREFERENCE_CONFIG.newton_steps == 25
    assert DEFAULT_PREFERENCE_CONFIG.pseudocount_kappa == 1.5
    assert DEFAULT_PREFERENCE_CONFIG.logistic_scale_s == 0.6


def test_default_config_is_frozen() -> None:
    with pytest.raises(ValidationError):
        DEFAULT_PREFERENCE_CONFIG.newton_steps = 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"version": "  "},
        {"newton_steps": 0},
        {"newton_damping": 0.0},
        {"newton_damping": -1.0},
        {"sigma_floor": 0.0},
        {"pseudocount_kappa": 0.0},
        {"logistic_scale_s": 0.0},
    ],
)
def test_invalid_overrides_are_rejected(overrides: dict[str, float | str]) -> None:
    with pytest.raises(ValidationError):
        PreferenceConfig(**overrides)  # type: ignore[arg-type]


def test_custom_config_is_accepted() -> None:
    config = PreferenceConfig(newton_steps=10, sigma_floor=0.1)
    assert config.newton_steps == 10
    assert config.sigma_floor == 0.1
