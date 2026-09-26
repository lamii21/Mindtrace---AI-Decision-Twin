"""Cross-cutting service-level failures - the ones ``api/errors.py`` maps to HTTP status codes.

Deliberately one shared vocabulary rather than one error type per service:
``docs/api/08-api-contracts.md`` s12's status map is itself shared across
every resource (``NotOwner``/``ResourceNotFound`` -> 404 everywhere, not a
per-resource 404 variant).
"""

from __future__ import annotations

from mindtrace.domain.errors import DomainError


class ServiceError(DomainError):
    """Base class for every service-layer failure."""


class ResourceNotFoundError(ServiceError):
    """The resource does not exist, or exists but is not owned by the caller.

    Deliberately the same error either way (``docs/api/08`` s1: "a mismatch
    is 404 (not 403) - don't confirm existence").
    """


class EmailAlreadyRegisteredError(ServiceError):
    """Registration failed because the email is already in use."""


class IdempotencyKeyConflictError(ServiceError):
    """The same ``Idempotency-Key`` was reused with a different request body."""


class SituationFrozenError(ServiceError):
    """A decision's situation fields are immutable once ``status >= simulated``."""


class InvalidStatusTransitionError(ServiceError):
    """The requested ``status`` is not reachable.

    Either from the record's current state, or (in M6) not reachable at all
    - e.g. ``simulated`` requires M7's engine.
    """


class InvalidChosenOptionError(ServiceError):
    """``chosen_option`` does not name one of the decision's own ``options``."""
