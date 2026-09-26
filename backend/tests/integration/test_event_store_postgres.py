"""`PostgresEventStore` against the shared `EventStore` contract (M6-Persistence
planning s16), plus the encryption-specific and crypto-shred end-to-end
proofs s26 asks for. Requires a real PostgreSQL 16 container."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from mindtrace.db.errors import KeyDestroyedError
from mindtrace.db.event_store import PostgresEventStore
from mindtrace.db.repositories.user_repository import create_user, destroy_user_data_key
from mindtrace.db.session import user_scoped_session
from mindtrace.domain.enums import MemoryType, ProvenanceSource, UserStatus
from mindtrace.domain.ids import UserId
from mindtrace.domain.user import User
from mindtrace.events.enums import MemoryEventType
from mindtrace.events.projectors.memory import fold_memory_events
from mindtrace.events.store import EventStore
from mindtrace.events.types import IngestedPayload
from mindtrace.security.keyring import generate_dek
from tests.integration.conftest import requires_docker
from tests.support.event_store_contract import FIXED_NOW, EventStoreContractTests

pytestmark = requires_docker


def _make_user(*, key_provider: object, email: str) -> User:
    user = User(
        id=UserId(uuid4()),
        email=email,
        password_hash="argon2id$placeholder",
        status=UserStatus.ACTIVE,
        data_key_ref=1,
        created_at=FIXED_NOW,
    )
    create_user(user=user, dek=generate_dek(), key_provider=key_provider)  # type: ignore[arg-type]
    return user


@pytest.mark.usefixtures("configured_engine")
class TestPostgresEventStoreContract(EventStoreContractTests):
    """The exact same behavioral contract `InMemoryEventStore` satisfies."""

    @pytest.fixture
    def store(self, key_provider: object) -> EventStore:
        return PostgresEventStore(key_provider=key_provider)  # type: ignore[arg-type]

    @pytest.fixture
    def user_a(self, key_provider: object) -> UserId:
        return _make_user(key_provider=key_provider, email=f"a-{uuid4()}@example.test").id

    @pytest.fixture
    def user_b(self, key_provider: object) -> UserId:
        return _make_user(key_provider=key_provider, email=f"b-{uuid4()}@example.test").id


@pytest.mark.usefixtures("configured_engine")
class TestEncryptionAtRest:
    def test_raw_payload_column_does_not_contain_the_plaintext(self, key_provider: object) -> None:
        """Inspect raw database bytes, not the ORM-decoded value (s25 - do not
        inspect ORM-decoded values for this test)."""
        user = _make_user(key_provider=key_provider, email=f"raw-{uuid4()}@example.test")
        store = PostgresEventStore(key_provider=key_provider)  # type: ignore[arg-type]
        secret = "a very specific secret phrase nobody else writes: xyzzy-42"
        store.append(
            user_id=user.id,
            payload=IngestedPayload(content=secret, memory_type=MemoryType.EPISODIC),
            source=ProvenanceSource.DECLARED,
            now=FIXED_NOW,
        )

        with user_scoped_session(user.id) as session:
            raw: bytes = session.execute(
                text("SELECT payload FROM memory_event WHERE user_id = :uid"),
                {"uid": str(user.id)},
            ).scalar_one()
        assert secret.encode("utf-8") not in bytes(raw)

    def test_key_destruction_makes_historical_payload_unreadable(
        self, key_provider: object
    ) -> None:
        """Crypto-shred: destroying the wrapped DEK makes prior events unreadable
        without deleting or modifying the append-only event row (s26)."""
        user = _make_user(key_provider=key_provider, email=f"shred-{uuid4()}@example.test")
        store = PostgresEventStore(key_provider=key_provider)  # type: ignore[arg-type]
        store.append(
            user_id=user.id,
            payload=IngestedPayload(
                content="soon to be unreadable", memory_type=MemoryType.EPISODIC
            ),
            source=ProvenanceSource.DECLARED,
            now=FIXED_NOW,
        )

        destroyed = destroy_user_data_key(
            user_id=user.id, key_version=1, destroyed_at=datetime.now(UTC)
        )
        assert destroyed is True

        with pytest.raises(KeyDestroyedError):
            store.read_stream(user.id)

        # The row itself is untouched - a fresh key at a NEW version can be
        # added without the event row ever having been mutated or removed.
        with user_scoped_session(user.id) as session:
            count: int = session.execute(
                text("SELECT count(*) FROM memory_event WHERE user_id = :uid"),
                {"uid": str(user.id)},
            ).scalar_one()
        assert count == 1

    def test_event_replay_through_the_existing_projector_is_unchanged(
        self, key_provider: object
    ) -> None:
        """End to end: domain Event -> append -> encrypted DB payload -> read_stream
        -> identical domain Event -> the existing, unmodified projector (s26)."""
        user = _make_user(key_provider=key_provider, email=f"replay-{uuid4()}@example.test")
        store = PostgresEventStore(key_provider=key_provider)  # type: ignore[arg-type]
        appended = store.append(
            user_id=user.id,
            payload=IngestedPayload(content="I value autonomy.", memory_type=MemoryType.SEMANTIC),
            source=ProvenanceSource.DECLARED,
            now=FIXED_NOW,
        )

        stream = store.read_stream(user.id)
        assert stream == (appended,)
        assert stream[0].type is MemoryEventType.INGESTED

        state = fold_memory_events(user.id, stream)
        (memory,) = state.active_memories
        assert memory.content == "I value autonomy."
        assert memory.origin_event_seq == 1
