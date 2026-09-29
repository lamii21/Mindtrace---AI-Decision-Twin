"""``/v1/decisions`` (``docs/api/08`` s4). ``/v1/simulate`` itself lives in ``simulate.py`` (M7)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status

from mindtrace.api.deps import get_current_user_id, get_key_provider, now
from mindtrace.api.idempotency import fingerprint
from mindtrace.api.pagination import DEFAULT_LIMIT, MAX_LIMIT, paginate
from mindtrace.api.routers.simulate import to_simulation_out
from mindtrace.api.schemas.common import Page
from mindtrace.api.schemas.decision import (
    DecisionCategoryIn,
    DecisionCreate,
    DecisionOut,
    DecisionPatch,
    DecisionStatusOut,
    OptionIn,
)
from mindtrace.api.schemas.simulation import SimulationSummary
from mindtrace.db.crypto import KeyProvider
from mindtrace.domain.decision_record import Decision, DecisionOption
from mindtrace.domain.enums import DecisionCategory, DecisionStatus
from mindtrace.domain.ids import DecisionId, UserId
from mindtrace.services import decision_service, idempotency_service
from mindtrace.services.errors import IdempotencyKeyConflictError

router = APIRouter(prefix="/v1/decisions", tags=["decisions"])

_ROUTE_CREATE = "POST /v1/decisions"


def _to_out(decision: Decision) -> DecisionOut:
    return DecisionOut(
        id=decision.id,
        title=decision.title,
        category=decision.category.value,
        context=decision.context,
        options=[OptionIn(id=o.id, label=o.label, body=o.body) for o in decision.options],
        status=decision.status.value,
        extracted_factors=None,
        extraction_model_run_id=None,
        chosen_option=decision.chosen_option,
        reasoning=decision.reasoning,
        decided_at=decision.decided_at,
        latest_prediction=None,
        outcome=None,
        created_at=decision.created_at,
    )


@router.post("", response_model=DecisionOut, status_code=status.HTTP_201_CREATED)
def create_decision(
    body: DecisionCreate,
    user_id: UserId = Depends(get_current_user_id),
    key_provider: KeyProvider = Depends(get_key_provider),
    request_time: datetime = Depends(now),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> DecisionOut:
    """Create a new decision (draft, or committed if logged retrospectively).

    A sequential retry (same ``Idempotency-Key``, request already completed)
    is checked for *before* creating anything, so it truly "creates nothing
    new" rather than creating a second decision and only detecting the
    duplicate afterwards.
    """
    fp = fingerprint(body.model_dump(mode="json"))
    if idempotency_key is not None:
        existing = idempotency_service.check_existing(
            user_id=user_id, route=_ROUTE_CREATE, idempotency_key=idempotency_key
        )
        if existing is not None:
            _ensure_fingerprint_matches(existing.request_fingerprint, fp)
            decision = decision_service.get(
                user_id, DecisionId(existing.resource_id), key_provider=key_provider
            )
            return _to_out(decision)

    decision = decision_service.create(
        user_id=user_id,
        title=body.title,
        category=DecisionCategory(body.category),
        context=body.context,
        options=tuple(DecisionOption(id=o.id, label=o.label, body=o.body) for o in body.options),
        decided_at=body.decided_at,
        chosen_option=body.chosen_option,
        key_provider=key_provider,
        now=request_time,
    )
    if idempotency_key is not None:
        decision = _claim(
            user_id=user_id,
            idempotency_key=idempotency_key,
            fingerprint_value=fp,
            decision=decision,
            now=request_time,
            key_provider=key_provider,
        )
    return _to_out(decision)


def _ensure_fingerprint_matches(existing_fingerprint: str, request_fingerprint: str) -> None:
    if existing_fingerprint != request_fingerprint:
        msg = "Idempotency-Key reused with a different request body"
        raise IdempotencyKeyConflictError(msg)


def _claim(
    *,
    user_id: UserId,
    idempotency_key: str,
    fingerprint_value: str,
    decision: Decision,
    now: datetime,
    key_provider: KeyProvider,
) -> Decision:
    """Claim the just-created ``decision`` under ``idempotency_key``.

    A genuinely concurrent duplicate can lose this race (``claimed=False``)
    even though it created its own resource first - in that case both
    callers must observe the *same* resource id, so this replays the
    winner's decision instead of the caller's own (``api/idempotency.py``'s
    documented residual-orphan model).
    """
    result = idempotency_service.claim_or_replay(
        user_id=user_id,
        route=_ROUTE_CREATE,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint_value,
        resource_id=UUID(str(decision.id)),
        response_status=status.HTTP_201_CREATED,
        now=now,
    )
    if result.claimed:
        return decision
    assert result.existing is not None
    _ensure_fingerprint_matches(result.existing.request_fingerprint, fingerprint_value)
    return decision_service.get(
        user_id, DecisionId(result.existing.resource_id), key_provider=key_provider
    )


@router.get("", response_model=Page[DecisionOut])
def list_decisions(
    category: DecisionCategoryIn | None = None,
    status_: DecisionStatusOut | None = Query(default=None, alias="status"),
    cursor: str | None = None,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    user_id: UserId = Depends(get_current_user_id),
    key_provider: KeyProvider = Depends(get_key_provider),
) -> Page[DecisionOut]:
    """List the caller's decisions, optionally filtered by ``category``/``status``."""
    results = decision_service.list_decisions(
        user_id=user_id,
        key_provider=key_provider,
        category=DecisionCategory(category) if category is not None else None,
        status=DecisionStatus(status_) if status_ is not None else None,
    )
    page, next_cursor = paginate(
        results,
        sort_key=lambda d: (d.created_at.isoformat(), str(d.id)),
        cursor=cursor,
        limit=limit,
    )
    return Page(items=[_to_out(d) for d in page], next_cursor=next_cursor)


@router.get("/{decision_id}", response_model=DecisionOut)
def get_decision(
    decision_id: UUID,
    user_id: UserId = Depends(get_current_user_id),
    key_provider: KeyProvider = Depends(get_key_provider),
) -> DecisionOut:
    """Return one of the caller's own decisions."""
    decision = decision_service.get(user_id, DecisionId(decision_id), key_provider=key_provider)
    return _to_out(decision)


@router.patch("/{decision_id}", response_model=DecisionOut)
def patch_decision(
    decision_id: UUID,
    body: DecisionPatch,
    user_id: UserId = Depends(get_current_user_id),
    key_provider: KeyProvider = Depends(get_key_provider),
    request_time: datetime = Depends(now),
) -> DecisionOut:
    """Apply a partial update to a decision's mutable fields."""
    decision = decision_service.patch(
        user_id=user_id,
        decision_id=DecisionId(decision_id),
        chosen_option=body.chosen_option,
        reasoning=body.reasoning,
        status=DecisionStatus(body.status) if body.status is not None else None,
        key_provider=key_provider,
        now=request_time,
    )
    return _to_out(decision)


@router.get("/{decision_id}/simulations", response_model=Page[SimulationSummary])
def list_simulations(
    decision_id: UUID,
    cursor: str | None = None,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    user_id: UserId = Depends(get_current_user_id),
    key_provider: KeyProvider = Depends(get_key_provider),
) -> Page[SimulationSummary]:
    """Every simulation run against one of the caller's own decisions, newest first."""
    pairs = decision_service.list_simulations(
        user_id, DecisionId(decision_id), key_provider=key_provider
    )
    page, next_cursor = paginate(
        pairs,
        sort_key=lambda pair: (pair[0].created_at.isoformat(), str(pair[0].id)),
        cursor=cursor,
        limit=limit,
    )
    items = [to_simulation_out(user_id, simulation, prediction) for simulation, prediction in page]
    return Page(items=items, next_cursor=next_cursor)
