"""`ExtractionConfig`'s own invariants."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mindtrace.llm.config import ExtractionConfig
from mindtrace.llm.prompts import PROMPT_VERSION


def test_defaults_pin_the_current_prompt_version_and_zero_temperature() -> None:
    config = ExtractionConfig(provider="fake", model="fake-v1")
    assert config.prompt_version == PROMPT_VERSION
    assert config.temperature == 0.0
    assert config.extraction_schema_version == "1"


def test_provider_and_model_are_required() -> None:
    with pytest.raises(ValidationError):
        ExtractionConfig()  # type: ignore[call-arg]


def test_is_frozen() -> None:
    config = ExtractionConfig(provider="fake", model="fake-v1")
    with pytest.raises(ValidationError):
        config.provider = "anthropic"


@pytest.mark.parametrize(
    "overrides",
    [
        {"provider": "  "},
        {"model": "  "},
        {"prompt_version": "  "},
        {"extraction_schema_version": "  "},
        {"temperature": -0.1},
        {"temperature": 2.1},
    ],
)
def test_invalid_overrides_are_rejected(overrides: dict[str, float | str]) -> None:
    base: dict[str, float | str] = {"provider": "fake", "model": "fake-v1"}
    base.update(overrides)
    with pytest.raises(ValidationError):
        ExtractionConfig(**base)  # type: ignore[arg-type]
