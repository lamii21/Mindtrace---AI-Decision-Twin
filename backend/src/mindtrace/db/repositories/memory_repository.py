"""Persistence for AG-3's ``Memory`` projection.

Proves that a :class:`~mindtrace.domain.memory.Memory` produced by the
existing, unmodified ``fold_memory_events`` projector can be written encrypted
and read back byte-identical - this milestone's acceptance criterion for
"encrypted event data can be read, decrypted, and replayed through the
existing projector" (M6-Persistence/Foundation planning s17). Nothing here
changes the projector; this module only persists its output.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mindtrace.db.crypto import KeyProvider, decrypt_field, encrypt_field
from mindtrace.db.dek_resolution import current_key_version, resolve_dek
from mindtrace.db.models.memory import MemoryModel
from mindtrace.db.session import user_scoped_session
from mindtrace.db.types import unpack_envelope
from mindtrace.domain.enums import MemoryType, ProvenanceSource
from mindtrace.domain.ids import MemoryId, UserId
from mindtrace.domain.memory import Memory

_TABLE = "memory"
_COLUMN = "content"


def upsert_memory(*, memory: Memory, key_provider: KeyProvider) -> None:
    """Insert or replace one projected memory row (a ``MemoryProjector`` write)."""
    with user_scoped_session(memory.user_id) as session:
        key_version = current_key_version(session, user_id=memory.user_id)
        dek = resolve_dek(
            session, user_id=memory.user_id, key_version=key_version, key_provider=key_provider
        )
        envelope = encrypt_field(
            memory.content,
            dek=dek,
            table=_TABLE,
            column=_COLUMN,
            user_id=memory.user_id,
            row_id=memory.id,
            key_version=key_version,
        )
        existing = session.get(MemoryModel, memory.id)
        if existing is None:
            session.add(_to_model(memory, envelope))
        else:
            _apply_to_model(existing, memory, envelope)


def get_memory(user_id: UserId, memory_id: MemoryId, *, key_provider: KeyProvider) -> Memory | None:
    """Return one memory, decrypted, or ``None`` if it does not exist / is not visible (RLS)."""
    with user_scoped_session(user_id) as session:
        row = session.get(MemoryModel, memory_id)
        if row is None:
            return None
        return _decrypt(row, session=session, user_id=user_id, key_provider=key_provider)


def list_memories(user_id: UserId, *, key_provider: KeyProvider) -> tuple[Memory, ...]:
    """Every memory row for ``user_id``, decrypted, current or not."""
    with user_scoped_session(user_id) as session:
        rows = (
            session.execute(select(MemoryModel).where(MemoryModel.user_id == user_id))
            .scalars()
            .all()
        )
        return tuple(
            _decrypt(row, session=session, user_id=user_id, key_provider=key_provider)
            for row in rows
        )


def _to_model(memory: Memory, envelope: bytes) -> MemoryModel:
    return MemoryModel(
        id=memory.id,
        user_id=memory.user_id,
        type=memory.type.value,
        content=envelope,
        source=memory.source.value,
        occurred_at=memory.occurred_at,
        origin_event_seq=memory.origin_event_seq,
        superseded_by=memory.superseded_by,
        deleted_at=memory.deleted_at,
        deleted_by_event_seq=memory.deleted_by_event_seq,
        projector_version=memory.projector_version,
    )


def _apply_to_model(existing: MemoryModel, memory: Memory, envelope: bytes) -> None:
    existing.content = envelope
    existing.superseded_by = memory.superseded_by
    existing.deleted_at = memory.deleted_at
    existing.deleted_by_event_seq = memory.deleted_by_event_seq


def _decrypt(
    row: MemoryModel, *, session: Session, user_id: UserId, key_provider: KeyProvider
) -> Memory:
    _format_version, key_version, _nonce, _ciphertext = unpack_envelope(row.content)
    dek = resolve_dek(session, user_id=user_id, key_version=key_version, key_provider=key_provider)
    content = decrypt_field(
        row.content, dek=dek, table=_TABLE, column=_COLUMN, user_id=user_id, row_id=row.id
    )
    return Memory(
        id=MemoryId(row.id),
        user_id=user_id,
        type=MemoryType(row.type),
        content=content,
        source=ProvenanceSource(row.source),
        occurred_at=row.occurred_at,
        origin_event_seq=row.origin_event_seq,
        superseded_by=MemoryId(row.superseded_by) if row.superseded_by is not None else None,
        deleted_at=row.deleted_at,
        deleted_by_event_seq=row.deleted_by_event_seq,
        projector_version=row.projector_version,
    )
