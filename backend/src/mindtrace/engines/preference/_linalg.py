"""A small, dependency-free dense linear solve for the Newton step's Hessian system.

No numpy/scipy: the dimension here is at most the trait count (19 weights,
spec/04 §2 table), and the interview/decision workload is "tens" of
observations (roadmap M4's own performance note) - Gauss-Jordan elimination
is `O(n^3)` on a `19x19` matrix, a fraction of a millisecond, and a plain
Python implementation keeps the engine's only dependency the standard
library, matching M3's precedent of not reaching for a numerical framework
until the problem actually needs one.
"""

from __future__ import annotations

from mindtrace.engines.preference.errors import PreferenceValidationError

_PIVOT_FLOOR = 1e-300


def solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Solve `matrix @ x = vector` via Gauss-Jordan elimination with partial pivoting.

    `matrix` must be square; callers (the Newton step) guarantee it is
    positive-definite (prior precision alone keeps the diagonal strictly
    positive even when the likelihood's own contribution is singular).

    Raises:
        PreferenceValidationError: if no usable pivot is found - would only
            happen if a caller passed a genuinely singular system.
    """
    n = len(vector)
    augmented = [[*row, vector[i]] for i, row in enumerate(matrix)]

    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(augmented[r][col]))
        if abs(augmented[pivot_row][col]) < _PIVOT_FLOOR:
            msg = f"singular matrix: no usable pivot in column {col}"
            raise PreferenceValidationError(msg)
        augmented[col], augmented[pivot_row] = augmented[pivot_row], augmented[col]

        pivot = augmented[col][col]
        augmented[col] = [value / pivot for value in augmented[col]]

        for row in range(n):
            if row == col:
                continue
            factor = augmented[row][col]
            if factor == 0.0:
                continue
            augmented[row] = [augmented[row][k] - factor * augmented[col][k] for k in range(n + 1)]

    return [augmented[i][n] for i in range(n)]
