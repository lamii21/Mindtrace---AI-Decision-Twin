"""A PostgreSQL :class:`~mindtrace.events.store.EventStore` (ADR-001, ADR-009).

Implements the exact, unmodified ``EventStore`` Protocol - the rest of the
codebase keeps consuming ``append``/``read_stream`` without knowing whether
the adapter behind it is this one or
:class:`~mindtrace.events.in_memory_store.InMemoryEventStore`. Encryption
lives entirely below the Protocol boundary: on ``append``, a typed payload is
canonically serialised then encrypted before the row is written; on
``read_stream``, the stored ciphertext is authenticated, decrypted, and
parsed back into the same ``dict[str, Any]`` shape ``events.types.Event``
already expects. ``events/`` never sees a key, a nonce, or ciphertext.

**Sequence allocation (M6-Persistence planning s14).** ``seq`` is never
computed as ``SELECT max(seq) + 1`` - that has no concurrency protection: two
concurrent appends for the same user could both read the same max and
collide. Instead each user's next ``seq`` is a counter column,
``users.next_event_seq``, allocated with one atomic
``UPDATE users SET next_event_seq = next_event_seq + 1 WHERE id = :user_id
RETURNING next_event_seq - 1``. PostgreSQL takes a row-level lock on that
user's ``users`` row for the statement's duration: a second concurrent
append for the *same* user blocks until the first transaction commits or
rolls back (so it can never observe or allocate the same value), while
appends for *different* users lock different rows and proceed fully in
parallel. Because the counter update and the event insert share one
transaction, a rolled-back append reverts the counter too - no permanent gap
is ever created by a failed append.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update

from mindtrace.db.crypto import KeyProvider, decrypt_field, encrypt_field
from mindtrace.db.dek_resolution import resolve_dek
from mindtrace.db.errors import UnknownUserError
from mindtrace.db.models.memory_event import MemoryEventModel
from mindtrace.db.models.user import UserModel
from mindtrace.db.session import user_scoped_session
from mindtrace.db.types import unpack_envelope
from mindtrace.domain.enums import ProvenanceSource
from mindtrace.domain.ids import EventId, UserId
from mindtrace.events.enums import MemoryEventType
from mindtrace.events.types import Event, EventPayload

_PAYLOAD_TABLE = "memory_event"
_PAYLOAD_COLUMN = "payload"


class PostgresEventStore:
    """Implements :class:`mindtrace.events.store.EventStore` against PostgreSQL."""

    def __init__(
        self, *, key_provider: KeyProvider, id_factory: Callable[[], UUID] = uuid4
    ) -> None:
        """Build a store bound to ``key_provider``.

        ``id_factory`` is injectable so tests can make event ids predictable,
        mirroring :class:`~mindtrace.events.in_memory_store.InMemoryEventStore`.
        """
        self._key_provider = key_provider
        self._id_factory = id_factory

    def append(
        self,
        *,
        user_id: UserId,
        payload: EventPayload,
        source: ProvenanceSource,
        now: datetime,
        occurred_at: date | None = None,
        causation_id: EventId | None = None,
        correlation_id: UUID | None = None,
    ) -> Event:
        """See :meth:`mindtrace.events.store.EventStore.append`."""
        event_id = EventId(self._id_factory())
        canonical_json = json.dumps(
            payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )

        with user_scoped_session(user_id) as session:
            user_row = session.get(UserModel, user_id)
            if user_row is None:
                msg = f"no user {user_id}"
                raise UnknownUserError(msg)
            key_version = user_row.data_key_ref
            dek = resolve_dek(
                session, user_id=user_id, key_version=key_version, key_provider=self._key_provider
            )

            allocated_seq = (
                session.execute(
                    update(UserModel)
                    .where(UserModel.id == user_id)
                    .values(next_event_seq=UserModel.next_event_seq + 1)
                    .returning(UserModel.next_event_seq)
                ).scalar_one()
                - 1
            )

            envelope = encrypt_field(
                canonical_json,
                dek=dek,
                table=_PAYLOAD_TABLE,
                column=_PAYLOAD_COLUMN,
                user_id=user_id,
                row_id=event_id,
                key_version=key_version,
            )
            session.add(
                MemoryEventModel(
                    id=event_id,
                    user_id=user_id,
                    seq=allocated_seq,
                    type=payload.event_type.value,
                    payload=envelope,
                    source=source.value,
                    occurred_at=occurred_at,
                    created_at=now,
                    causation_id=causation_id,
                    correlation_id=correlation_id,
                )
            )
            session.flush()

        return Event(
            id=event_id,
            user_id=user_id,
            seq=allocated_seq,
            type=payload.event_type,
            payload=json.loads(canonical_json),
            source=source,
            occurred_at=occurred_at,
            created_at=now,
            causation_id=causation_id,
            correlation_id=correlation_id,
        )

    def read_stream(self, user_id: UserId, *, since_seq: int = 0) -> tuple[Event, ...]:
        """See :meth:`mindtrace.events.store.EventStore.read_stream`."""
        with user_scoped_session(user_id) as session:
            user_row = session.get(UserModel, user_id)
            if user_row is None:
                return ()

            rows = (
                session.execute(
                    select(MemoryEventModel)
                    .where(MemoryEventModel.user_id == user_id, MemoryEventModel.seq > since_seq)
                    .order_by(MemoryEventModel.seq)
                )
                .scalars()
                .all()
            )

            dek_cache: dict[int, bytes] = {}
            events: list[Event] = []
            for row in rows:
                _format_version, key_version, _nonce, _ciphertext = unpack_envelope(row.payload)
                if key_version not in dek_cache:
                    dek_cache[key_version] = resolve_dek(
                        session,
                        user_id=user_id,
                        key_version=key_version,
                        key_provider=self._key_provider,
                    )
                plaintext = decrypt_field(
                    row.payload,
                    dek=dek_cache[key_version],
                    table=_PAYLOAD_TABLE,
                    column=_PAYLOAD_COLUMN,
                    user_id=user_id,
                    row_id=row.id,
                )
                causation_id = EventId(row.causation_id) if row.causation_id is not None else None
                events.append(
                    Event(
                        id=EventId(row.id),
                        user_id=user_id,
                        seq=row.seq,
                        type=MemoryEventType(row.type),
                        payload=json.loads(plaintext),
                        source=ProvenanceSource(row.source),
                        occurred_at=row.occurred_at,
                        created_at=row.created_at,
                        causation_id=causation_id,
                        correlation_id=row.correlation_id,
                    )
                )
            return tuple(events)
