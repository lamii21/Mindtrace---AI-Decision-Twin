"""Small numeric helpers shared across the confidence engine's pure functions."""

from __future__ import annotations

import math


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def stable_sigmoid(x: float) -> float:
    """`1 / (1 + e^-x)`, computed without overflow for large `|x|`."""
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)
