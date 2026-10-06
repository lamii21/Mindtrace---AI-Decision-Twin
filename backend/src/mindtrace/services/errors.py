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


class SimulationInProgressError(ServiceError):
    """A simulation for this ``Idempotency-Key`` was claimed but has not finished persisting yet.

    The narrow, honest residual of M7's reserve-before-compute idempotency
    design (``services/decision_service.py``'s ``simulate()``): the winner
    of a genuinely concurrent race is still running the (expensive) LLM
    call/orchestration when the loser's request arrives. Rather than block
    the request or silently run a second LLM call, this reports the
    in-flight state plainly - the caller retries.
    """


class InvalidInterviewItemError(ServiceError):
    """An answer names an ``item_id`` that is not in the current interview bank."""


class SessionAlreadyFinalizedError(ServiceError):
    """The session has already been finalized - answers/finalize can no longer be submitted."""


class InterviewNotCompleteError(ServiceError):
    """``:finalize`` was called before every fixed-order item has an answer."""


class MemoryAlreadyDeletedError(ServiceError):
    """A deletion (preview or apply) named a memory that is already tombstoned."""


class UnsupportedBeliefTypeError(ServiceError):
    """``POST /v1/beliefs/{type}/{id}:dispute`` named a ``belief_type`` M9 cannot recompute.

    Only ``preference``/``trait`` are recomputable via the existing M4
    preference engine (M9 planning - approved scope). ``decision_factor``/
    ``value``/``contradiction`` recompute through different, not-yet-wired
    paths and are deliberately refused rather than silently accepted.
    """


class StaleBeliefError(ServiceError):
    """A dispute named a ``belief_id`` that is not the caller's current ``TwinVersion``.

    Disputing a *historical* ``TwinVersion`` is refused outright -
    ``TwinVersion`` is immutable and a dispute can only ever produce a *new*
    one built on top of the current posterior, never retroactively revise an
    old snapshot (M8's own historical-reproducibility invariant, unchanged).
    """
