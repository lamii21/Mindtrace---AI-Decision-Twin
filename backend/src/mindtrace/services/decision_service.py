"""Decision CRUD (M6-API).

No simulation - that is M7's `.simulate()` method added to this same
service.

**Status on create** (AG-5, ``docs/architecture/02-domain-model.md``): a
decision with both ``decided_at`` and ``chosen_option`` set is a
*retrospective* log of a past choice and is created directly ``committed``;
otherwise it starts ``draft``. Nothing in M6 can ever produce ``simulated``
(that needs M7's engine call) or transition an existing decision back to
``draft``.

**Situation-freeze** (``docs/api/08`` s4: "situation fields immutable once
status >= simulated"): enforced here even though M6 can never itself reach
``simulated`` - the guard exists now so M7 does not have to retrofit it, and
so the invariant is testable today via a decision constructed already at
that status (a fixture, not a code path M6 itself can reach).

``GET /v1/decisions/{id}/simulations`` truthfully returns an empty page in
M6 - no ``Simulation`` table exists yet (M7).
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from mindtrace.db.crypto import KeyProvider
from mindtrace.db.repositories import decision_repository
from mindtrace.domain.decision_record import Decision, DecisionOption
from mindtrace.domain.enums import DecisionCategory, DecisionStatus
from mindtrace.domain.ids import DecisionId, UserId
from mindtrace.services.errors import (
    InvalidChosenOptionError,
    InvalidStatusTransitionError,
    ResourceNotFoundError,
)

_PATCH_REACHABLE_STATUSES = frozenset({DecisionStatus.COMMITTED, DecisionStatus.ARCHIVED})


def create(
    *,
    user_id: UserId,
    title: str,
    category: DecisionCategory,
    context: str,
    options: tuple[DecisionOption, ...],
    decided_at: datetime | None,
    chosen_option: str | None,
    key_provider: KeyProvider,
    now: datetime,
) -> Decision:
    """Create a new decision.

    Raises:
        InvalidChosenOptionError: ``chosen_option`` does not name one of
            ``options``.
    """
    if chosen_option is not None:
        _validate_chosen_option(chosen_option, options)
    status = (
        DecisionStatus.COMMITTED
        if decided_at is not None and chosen_option is not None
        else DecisionStatus.DRAFT
    )
    decision = Decision(
        id=DecisionId(uuid4()),
        user_id=user_id,
        title=title,
        category=category,
        context=context,
        options=options,
        chosen_option=chosen_option,
        reasoning=None,
        decided_at=decided_at,
        status=status,
        created_at=now,
    )
    decision_repository.create_decision(decision=decision, key_provider=key_provider)
    return decision


def get(user_id: UserId, decision_id: DecisionId, *, key_provider: KeyProvider) -> Decision:
    """Return one decision.

    Raises:
        ResourceNotFoundError: it does not exist, or is not owned by
            ``user_id`` (RLS makes the two indistinguishable - by design).
    """
    decision = decision_repository.get_decision(user_id, decision_id, key_provider=key_provider)
    if decision is None:
        msg = f"decision {decision_id} not found"
        raise ResourceNotFoundError(msg)
    return decision


def list_decisions(
    *,
    user_id: UserId,
    key_provider: KeyProvider,
    category: DecisionCategory | None = None,
    status: DecisionStatus | None = None,
) -> tuple[Decision, ...]:
    """Every decision for ``user_id`` matching the given filters."""
    return decision_repository.list_decisions(
        user_id, key_provider=key_provider, category=category, status=status
    )


def patch(
    *,
    user_id: UserId,
    decision_id: DecisionId,
    chosen_option: str | None,
    reasoning: str | None,
    status: DecisionStatus | None,
    key_provider: KeyProvider,
    now: datetime,
) -> Decision:
    """Apply a partial update to a decision's mutable fields.

    Raises:
        ResourceNotFoundError: as :func:`get`.
        InvalidChosenOptionError: ``chosen_option`` does not name one of the
            decision's own options.
        InvalidStatusTransitionError: ``status`` is not one M6 can honestly
            produce (``simulated`` needs M7), or is not reachable from the
            current status.

    Note: ``docs/api/08`` s4's situation-freeze rule ("immutable once status
    >= simulated") applies to ``title``/``category``/``context``/``options``
    - fields ``DecisionPatch`` never carries in the first place, so M6's
    PATCH has nothing to freeze. M7's own service method will need the guard
    once a route can submit those fields again (it cannot, here).
    """
    current = get(user_id, decision_id, key_provider=key_provider)

    next_chosen_option = chosen_option if chosen_option is not None else current.chosen_option
    if next_chosen_option is not None:
        _validate_chosen_option(next_chosen_option, current.options)

    next_status = status if status is not None else current.status
    if status is not None and status != current.status:
        _validate_transition(current.status, status)

    next_reasoning = reasoning if reasoning is not None else current.reasoning
    becomes_committed = next_status is DecisionStatus.COMMITTED and current.decided_at is None
    next_decided_at = now if becomes_committed else current.decided_at

    updated = decision_repository.update_decision(
        user_id=user_id,
        decision_id=decision_id,
        chosen_option=next_chosen_option,
        reasoning=next_reasoning,
        status=next_status,
        decided_at=next_decided_at,
        key_provider=key_provider,
    )
    if updated is None:  # pragma: no cover - existence already confirmed by get() above
        msg = f"decision {decision_id} not found"
        raise ResourceNotFoundError(msg)
    return updated


def list_simulations(
    user_id: UserId, decision_id: DecisionId, *, key_provider: KeyProvider
) -> tuple[object, ...]:
    """Always empty in M6.

    Confirms ownership (raises :class:`~mindtrace.services.errors.
    ResourceNotFoundError` if not), then returns nothing - no ``Simulation``
    table exists yet (M7).
    """
    get(user_id, decision_id, key_provider=key_provider)
    return ()


def _validate_chosen_option(chosen_option: str, options: tuple[DecisionOption, ...]) -> None:
    if chosen_option not in {option.id for option in options}:
        msg = f"chosen_option {chosen_option!r} does not name one of this decision's options"
        raise InvalidChosenOptionError(msg)


def _validate_transition(current: DecisionStatus, target: DecisionStatus) -> None:
    if target is DecisionStatus.SIMULATED:
        msg = "status cannot be set to 'simulated' directly - that requires M7's simulate engine"
        raise InvalidStatusTransitionError(msg)
    if target not in _PATCH_REACHABLE_STATUSES:
        msg = f"status {target} is not a valid PATCH target"
        raise InvalidStatusTransitionError(msg)
    if current is DecisionStatus.ARCHIVED:
        msg = "an archived decision's status cannot be changed"
        raise InvalidStatusTransitionError(msg)
