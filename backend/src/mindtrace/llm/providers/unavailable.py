"""The default production ``LLMClient`` when no real provider is configured (M7 planning s9).

This build ships no real provider adapter (only ``providers/fake.py``, which
is test-only: it must be scripted with canned responses ahead of time and
cannot sensibly answer an arbitrary real user's decision context). Rather
than silently add a third-party SDK, or misuse ``FakeLLMClient`` with a
fabricated "found nothing" success, ``/v1/simulate``'s default DI wiring
uses this: every call truthfully fails closed as
:class:`~mindtrace.llm.errors.ProviderUnavailableError` - the exact,
already-typed, already-tested failure mode ``llm.extraction.extract_factors``
turns into a ``failed`` ``ExtractionOutcome`` (all factors ``known=False``),
which MCDA's own coverage gate then resolves to ``UNCERTAIN``. Swapping in a
real provider later needs only a new class implementing ``LLMClient`` and a
one-line change to ``api/deps.get_llm_client`` - ADR-003's whole point.
"""

from __future__ import annotations

from mindtrace.llm.errors import ProviderUnavailableError


class UnavailableLLMClient:
    """Implements ``LLMClient``; every call raises ``ProviderUnavailableError``."""

    def generate(self, *, system_prompt: str, user_content: str) -> str:
        """Never returns - see module docstring.

        Raises:
            mindtrace.llm.errors.ProviderUnavailableError: always.
        """
        del system_prompt, user_content
        msg = "no real LLM provider is configured in this build"
        raise ProviderUnavailableError(msg)
