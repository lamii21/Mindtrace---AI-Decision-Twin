"""The deterministic MCDA decision engine (ADR-002, ``docs/spec/05-mcda-mathematics.md``).

Pure functions only: same inputs + the same :class:`~mindtrace.engines.mcda.config.MCDAConfig`
version always produce a byte-identical :class:`~mindtrace.domain.decision.DecisionResult`.
No LLM, no persistence, no confidence (that gate is a later milestone's - see
``decide.py``'s module docstring).
"""

from __future__ import annotations

from mindtrace.engines.mcda.config import DEFAULT_MCDA_CONFIG, ENGINE_VERSION, MCDAConfig
from mindtrace.engines.mcda.decide import decide, decide_multi_option
from mindtrace.engines.mcda.errors import MCDAValidationError

__all__ = [
    "DEFAULT_MCDA_CONFIG",
    "ENGINE_VERSION",
    "MCDAConfig",
    "MCDAValidationError",
    "decide",
    "decide_multi_option",
]
