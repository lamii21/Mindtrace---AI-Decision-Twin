"""The in-memory decision simulation orchestrator (M6-B).

A composition layer, not an intelligence layer: it calls M5 extraction,
M6-A projection, M3 MCDA, and M4 confidence through their existing public
contracts and returns their results unmodified. See
``simulation.py``'s module docstring for the full pipeline and
``docs/adr/ADR-002-deterministic-mcda-decision-engine.md``/``ADR-003``/
``ADR-005``/``ADR-006`` for the mathematics each engine actually owns.
"""

from __future__ import annotations

from mindtrace.orchestration.errors import SimulationError
from mindtrace.orchestration.simulation import (
    SIMULATION_VERSION,
    SimulationConfig,
    SimulationResult,
    simulate,
)

__all__ = [
    "SIMULATION_VERSION",
    "SimulationConfig",
    "SimulationError",
    "SimulationResult",
    "simulate",
]
