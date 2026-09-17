"""`solve`: the Newton step's dense linear solver."""

from __future__ import annotations

import pytest

from mindtrace.engines.preference._linalg import solve
from mindtrace.engines.preference.errors import PreferenceValidationError


def test_solves_a_1x1_system() -> None:
    assert solve([[2.0]], [4.0]) == pytest.approx([2.0])


def test_solves_a_diagonal_system() -> None:
    result = solve([[2.0, 0.0], [0.0, 4.0]], [6.0, 8.0])
    assert result == pytest.approx([3.0, 2.0])


def test_solves_a_dense_symmetric_system() -> None:
    # x + y = 3, x - y = 1 -> x=2, y=1
    result = solve([[1.0, 1.0], [1.0, -1.0]], [3.0, 1.0])
    assert result == pytest.approx([2.0, 1.0])


def test_solves_a_3x3_system_requiring_pivoting() -> None:
    # A tiny leading pivot forces a row swap.
    matrix = [[1e-10, 1.0, 0.0], [1.0, 1.0, 1.0], [0.0, 1.0, 2.0]]
    vector = [1.0, 3.0, 3.0]
    result = solve(matrix, vector)
    for row, expected in zip(matrix, vector, strict=True):
        assert sum(a * x for a, x in zip(row, result, strict=True)) == pytest.approx(expected)


def test_identity_matrix_returns_the_vector_unchanged() -> None:
    result = solve([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], [5.0, -2.0, 0.5])
    assert result == pytest.approx([5.0, -2.0, 0.5])


def test_singular_matrix_raises() -> None:
    with pytest.raises(PreferenceValidationError, match="singular"):
        solve([[1.0, 2.0], [2.0, 4.0]], [1.0, 2.0])


def test_does_not_mutate_the_input_matrix() -> None:
    matrix = [[2.0, 0.0], [0.0, 4.0]]
    original = [row[:] for row in matrix]
    solve(matrix, [6.0, 8.0])
    assert matrix == original
