"""Confidence-engine-specific validation failures.

A distinct, catchable type (still a :class:`~mindtrace.domain.errors.DomainError`)
for the invariants that depend on context the domain types alone can't check -
e.g. an :class:`~mindtrace.domain.confidence.ExtractionSignal` that is
internally consistent but doesn't cover the decision's actual known-factor set.
"""

from __future__ import annotations

from mindtrace.domain.errors import DomainError


class ConfidenceValidationError(DomainError):
    """A confidence engine input violates an invariant the mathematics assumes."""
