"""``/v1/memories`` (``docs/api/08`` s3).

``POST /v1/memories:forget`` (topic-based deletion) is **not implemented** -
see ``services/memory_service.py``'s module docstring for why (it needs
semantic matching over memory content, which needs embeddings that do not
exist yet). Explicit-id deletion (``DELETE /v1/memories/{id}``) is fully
implemented.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status

from mindtrace.api.deps import get_current_user_id, get_key_provider, now
from mindtrace.api.idempotency import fingerprint
from mindtrace.api.pagination import DEFAULT_LIMIT, MAX_LIMIT, paginate
from mindtrace.api.schemas.common import Page
from mindtrace.api.schemas.memory import (
    DeletionPlan,
    JobAccepted,
    MemoryAccepted,
    MemoryCreate,
    MemoryOut,
    MemorySourceIn,
    MemoryTypeOut,
)
from mindtrace.db.crypto import KeyProvider
from mindtrace.domain.enums import MemoryType, ProvenanceSource
from mindtrace.domain.ids import MemoryId, UserId
from mindtrace.domain.memory import Memory
from mindtrace.services import idempotency_service, memory_service
from mindtrace.services.errors import IdempotencyKeyConflictError

router = APIRouter(prefix="/v1/memories", tags=["memories"])

_ROUTE_CREATE = "POST /v1/memories"


def _to_out(memory: Memory, created_at: datetime) -> MemoryOut:
    occurred_at = (
        datetime.combine(memory.occurred_at, datetime.min.time(), tzinfo=UTC)
        if memory.occurred_at is not None
        else None
    )
    return MemoryOut(
        id=memory.id,
        type=memory.type.value,
        text=memory.content,
        source=memory.source.value,
        confidence=1.0,  # AG-3: "1.0 for declared" - M6 never produces source=inferred memories
        occurred_at=occurred_at,
        created_at=created_at,
        origin_event_seq=memory.origin_event_seq,
        supports=[],  # no belief-producing engine is wired to the API in M6
        superseded_by=memory.superseded_by,
        deleted_at=memory.deleted_at,
    )


@router.post("", response_model=MemoryAccepted, status_code=status.HTTP_202_ACCEPTED)
def create_memory(
    body: MemoryCreate,
    user_id: UserId = Depends(get_current_user_id),
    key_provider: KeyProvider = Depends(get_key_provider),
    request_time: datetime = Depends(now),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> MemoryAccepted:
    """Append an ``ingested`` event and return its synchronously-projected memory.

    A sequential retry (same ``Idempotency-Key``, request already completed)
    is checked for *before* ingesting anything, so it truly "creates nothing
    new" rather than re-ingesting and only detecting the duplicate afterwards.
    """
    fp = fingerprint(body.model_dump(mode="json"))
    if idempotency_key is not None:
        existing = idempotency_service.check_existing(
            user_id=user_id, route=_ROUTE_CREATE, idempotency_key=idempotency_key
        )
        if existing is not None:
            _ensure_fingerprint_matches(existing.request_fingerprint, fp)
            memory, _created_at = memory_service.get(
                user_id, MemoryId(existing.resource_id), key_provider=key_provider
            )
            return _to_accepted(memory)

    source = ProvenanceSource(body.source)
    memory, _created_at = memory_service.ingest(
        user_id=user_id,
        kind=body.kind,
        text=body.text,
        source=source,
        key_provider=key_provider,
        now=request_time,
    )
    if idempotency_key is not None:
        memory = _claim(
            user_id=user_id,
            idempotency_key=idempotency_key,
            fingerprint_value=fp,
            memory=memory,
            now=request_time,
            key_provider=key_provider,
        )
    return _to_accepted(memory)


def _to_accepted(memory: Memory) -> MemoryAccepted:
    return MemoryAccepted(memory_event_id=memory.id, projection="done", memory_id=memory.id)


def _ensure_fingerprint_matches(existing_fingerprint: str, request_fingerprint: str) -> None:
    if existing_fingerprint != request_fingerprint:
        msg = "Idempotency-Key reused with a different request body"
        raise IdempotencyKeyConflictError(msg)


def _claim(
    *,
    user_id: UserId,
    idempotency_key: str,
    fingerprint_value: str,
    memory: Memory,
    now: datetime,
    key_provider: KeyProvider,
) -> Memory:
    """Claim the just-created ``memory`` under ``idempotency_key``.

    A genuinely concurrent duplicate can lose this race (``claimed=False``)
    even though it created its own resource first - in that case both
    callers must observe the *same* resource id, so this replays the
    winner's memory instead of the caller's own (``api/idempotency.py``'s
    documented residual-orphan model).
    """
    result = idempotency_service.claim_or_replay(
        user_id=user_id,
        route=_ROUTE_CREATE,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint_value,
        resource_id=UUID(str(memory.id)),
        response_status=status.HTTP_202_ACCEPTED,
        now=now,
    )
    if result.claimed:
        return memory
    assert result.existing is not None
    _ensure_fingerprint_matches(result.existing.request_fingerprint, fingerprint_value)
    winner, _created_at = memory_service.get(
        user_id, MemoryId(result.existing.resource_id), key_provider=key_provider
    )
    return winner


@router.get("", response_model=Page[MemoryOut])
def list_memories(
    type: MemoryTypeOut | None = None,  # noqa: A002
    source: MemorySourceIn | None = None,
    cursor: str | None = None,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    user_id: UserId = Depends(get_current_user_id),
    key_provider: KeyProvider = Depends(get_key_provider),
) -> Page[MemoryOut]:
    """List the caller's memories, optionally filtered by ``type``/``source``."""
    results = memory_service.list_memories(
        user_id=user_id,
        key_provider=key_provider,
        type_=MemoryType(type) if type is not None else None,
        source=ProvenanceSource(source) if source is not None else None,
    )
    page, next_cursor = paginate(
        results,
        sort_key=lambda pair: (pair[1].isoformat(), str(pair[0].id)),
        cursor=cursor,
        limit=limit,
    )
    items = [_to_out(memory, created_at) for memory, created_at in page]
    return Page(items=items, next_cursor=next_cursor)


@router.get("/{memory_id}", response_model=MemoryOut)
def get_memory(
    memory_id: UUID,
    user_id: UserId = Depends(get_current_user_id),
    key_provider: KeyProvider = Depends(get_key_provider),
) -> MemoryOut:
    """Return one of the caller's own memories."""
    memory, created_at = memory_service.get(user_id, MemoryId(memory_id), key_provider=key_provider)
    return _to_out(memory, created_at)


@router.delete("/{memory_id}")
def delete_memory(
    memory_id: UUID,
    response: Response,
    dry_run: bool = True,
    user_id: UserId = Depends(get_current_user_id),
    key_provider: KeyProvider = Depends(get_key_provider),
    request_time: datetime = Depends(now),
) -> DeletionPlan | JobAccepted:
    """Preview (``dry_run=true``) or apply deletion of one of the caller's own memories."""
    if dry_run:
        impact = memory_service.preview_delete(
            user_id=user_id, memory_ids=(MemoryId(memory_id),), key_provider=key_provider
        )
        response.status_code = status.HTTP_200_OK
        return DeletionPlan(
            target_memory_ids=list(impact.memory_ids),
            affected_beliefs=[],
            affected_traits=[],
            invalidated_predictions=0,
            twin_version_will_bump=False,
        )
    _impact, job_id = memory_service.apply_delete(
        user_id=user_id,
        memory_ids=(MemoryId(memory_id),),
        key_provider=key_provider,
        now=request_time,
    )
    response.status_code = status.HTTP_202_ACCEPTED
    return JobAccepted(job_id=job_id)
