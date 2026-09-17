"""MCDA-specific validation failures.

A distinct, catchable type (still a :class:`~mindtrace.domain.errors.DomainError`)
for the invariants that depend on context the domain types alone can't check -
e.g. a :class:`~mindtrace.domain.decision.WeightVector` that is internally
consistent (sums to 1) but doesn't cover the taxonomy's actual factor set.
"""

from __future__ import annotations

from mindtrace.domain.errors import DomainError


class MCDAValidationError(DomainError):
    """An MCDA engine input violates an invariant the mathematics assumes."""
