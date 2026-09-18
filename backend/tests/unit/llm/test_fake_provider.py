"""`FakeLLMClient` itself: the deterministic, network-free test double."""

from __future__ import annotations

from pathlib import Path

import pytest

import mindtrace.llm.providers.fake as fake_module
from mindtrace.llm.providers.fake import FakeLLMClient


def test_requires_either_responses_or_raises() -> None:
    with pytest.raises(ValueError, match="requires either"):
        FakeLLMClient()


def test_returns_the_scripted_response() -> None:
    client = FakeLLMClient(responses=["hello"])
    assert client.generate(system_prompt="s", user_content="u") == "hello"


def test_repeats_the_last_response_once_exhausted() -> None:
    client = FakeLLMClient(responses=["first", "second"])
    assert client.generate(system_prompt="s", user_content="u") == "first"
    assert client.generate(system_prompt="s", user_content="u") == "second"
    assert client.generate(system_prompt="s", user_content="u") == "second"
    assert client.generate(system_prompt="s", user_content="u") == "second"


def test_raises_are_raised_on_every_call() -> None:
    client = FakeLLMClient(raises=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        client.generate(system_prompt="s", user_content="u")
    with pytest.raises(RuntimeError, match="boom"):
        client.generate(system_prompt="s", user_content="u")


def test_records_every_call_for_injection_assertions() -> None:
    client = FakeLLMClient(responses=["ok"])
    client.generate(system_prompt="SYS", user_content="USER")
    assert client.calls == [("SYS", "USER")]


def test_never_touches_the_network() -> None:
    """No import of `socket`/`httpx`/`requests` anywhere in the fake provider module -
    this test is a structural smoke check, not a network sniffer."""
    source = fake_module.__file__
    assert source is not None
    contents = Path(source).read_text(encoding="utf-8")
    for forbidden in ("socket", "httpx", "requests", "urllib"):
        assert forbidden not in contents
