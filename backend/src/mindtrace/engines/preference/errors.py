"""Preference-engine-specific failures.

A distinct, catchable type (still a :class:`~mindtrace.domain.errors.DomainError`)
for the invariants that depend on context the domain types alone can't check -
e.g. a design vector referencing a factor outside the trait model's known set,
or a Newton step landing on a numerically singular system.
"""

from __future__ import annotations

from mindtrace.domain.errors import DomainError


class PreferenceValidationError(DomainError):
    """A preference engine input violates an invariant the mathematics assumes."""
