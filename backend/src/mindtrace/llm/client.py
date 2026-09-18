"""The provider-agnostic LLM interface (ADR-003).

A single `Protocol` - `extraction.py` and every other caller in this package
depend on this, never on a concrete provider SDK. `mindtrace.llm.providers` is
the only place a real provider adapter is allowed to live (`.importlinter`'s
`provider-sdks-isolated` contract); M5 ships only `providers/fake.py`, a
network-free deterministic implementation for tests.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Generates raw provider output for one structured-extraction call.

    Implementations must not raise arbitrary exceptions for an *expected*
    failure mode (no network, no response in time): wrap those in
    `mindtrace.llm.errors.ProviderUnavailableError`/`ProviderTimeoutError` so
    `extraction.py` can fail closed instead of propagating an unrecognised
    provider-specific exception type.
    """

    def generate(self, *, system_prompt: str, user_content: str) -> str:
        """Return the provider's raw text output for this call.

        Raises:
            mindtrace.llm.errors.ProviderUnavailableError: the provider could
                not be reached.
            mindtrace.llm.errors.ProviderTimeoutError: the provider did not
                respond in time.
        """
        ...  # pragma: no cover - a Protocol stub body, never actually executed
