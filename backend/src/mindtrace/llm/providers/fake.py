"""A deterministic, network-free `LLMClient` for tests (M5 §12).

Scripted per-instance: construct with either a fixed sequence of raw text
responses (consumed one per call, the last one repeating if a caller makes
more calls than were scripted - useful for exercising self-consistency's two
calls) or an exception to raise on every call (simulating a provider
failure). Never touches the network; CI needs no API key to run any test
that uses this.
"""

from __future__ import annotations

from collections.abc import Sequence


class FakeLLMClient:
    """Implements `mindtrace.llm.client.LLMClient` without a real provider."""

    def __init__(
        self,
        *,
        responses: Sequence[str] | None = None,
        raises: Exception | None = None,
    ) -> None:
        """Script this client with either `responses` or `raises` (at least one required)."""
        if not responses and raises is None:
            msg = "FakeLLMClient requires either a non-empty `responses` or `raises`"
            raise ValueError(msg)
        self._responses: tuple[str, ...] = tuple(responses) if responses else ()
        self._raises = raises
        self._call_count = 0
        self.calls: list[tuple[str, str]] = []

    def generate(self, *, system_prompt: str, user_content: str) -> str:
        """Record the call, then return the next scripted response or raise."""
        self.calls.append((system_prompt, user_content))
        if self._raises is not None:
            raise self._raises
        index = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return self._responses[index]
