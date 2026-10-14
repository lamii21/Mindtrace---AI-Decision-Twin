"""Parallel-twin decision simulation (M10; ADR-007).

Pure: re-parametrises the SAME MCDA engine (``engines.mcda.decide``) with N
different, deterministic ``WeightVector`` shifts - never a different code
path, a different prompt, or an LLM-generated weight. No persistence, no
HTTP, no clock reads.
"""

from __future__ import annotations

from mindtrace.engines.simulation.parallel import (
    apply_twin_transform,
    ensemble_observation_from,
    run_twin_ensemble,
)

__all__ = ["apply_twin_transform", "ensemble_observation_from", "run_twin_ensemble"]
