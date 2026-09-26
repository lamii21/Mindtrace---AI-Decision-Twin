"""Row-Level Security isolation and pooling-leakage.

M6-Persistence/Foundation planning s6/s20/s27/s28. Every assertion here runs
as ``mindtrace_app`` - a real, non-owner application role - never a
superuser/table owner (``configured_engine`` is already pointed at that
role; s20's own warning: "Do not test RLS using a superuser or table owner
that bypasses the policy and then claim it works.").
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from mindtrace.db import session as db_session
from mindtrace.db.event_store import PostgresEventStore
from mindtrace.db.repositories.decision_repository import create_decision
from mindtrace.db.repositories.memory_repository import get_memory, list_memories, upsert_memory
from mindtrace.db.repositories.user_repository import create_user
from mindtrace.db.session import get_session, user_scoped_session
from mindtrace.domain.decision_record import Decision, DecisionOption
from mindtrace.domain.enums import (
    DecisionCategory,
    DecisionStatus,
    MemoryType,
    ProvenanceSource,
    UserStatus,
)
from mindtrace.domain.ids import DecisionId, MemoryId, UserId
from mindtrace.domain.memory import Memory
from mindtrace.domain.user import User
from mindtrace.events.projectors.memory import MEMORY_PROJECTOR_VERSION
from mindtrace.events.types import IngestedPayload
from mindtrace.security.keyring import generate_dek
from tests.integration.conftest import requires_docker

pytestmark = requires_docker


def _make_user(*, key_provider: object, email: str) -> User:
    user = User(
        id=UserId(uuid4()),
        email=email,
        password_hash="argon2id$placeholder",
        status=UserStatus.ACTIVE,
        data_key_ref=1,
        created_at=datetime.now(UTC),
    )
    create_user(user=user, dek=generate_dek(), key_provider=key_provider)  # type: ignore[arg-type]
    return user


def _seed_memory_event(*, user: User, key_provider: object) -> None:
    store = PostgresEventStore(key_provider=key_provider)  # type: ignore[arg-type]
    store.append(
        user_id=user.id,
        payload=IngestedPayload(
            content=f"memory for {user.email}", memory_type=MemoryType.EPISODIC
        ),
        source=ProvenanceSource.DECLARED,
        now=datetime.now(UTC),
    )


def _seed_memory(*, user: User, key_provider: object) -> Memory:
    """Seed both a real originating ``memory_event`` and its projected ``memory`` row.

    ``memory.origin_event_seq`` must name a real ``memory_event`` row -
    ``get_memory``/``list_memories`` join on it for ``created_at`` (M6-API
    planning s9) - so this seeds the event first rather than fabricating a
    projection with no event behind it.
    """
    _seed_memory_event(user=user, key_provider=key_provider)
    memory = Memory(
        id=MemoryId(uuid4()),
        user_id=user.id,
        type=MemoryType.SEMANTIC,
        content=f"projected memory for {user.email}",
        source=ProvenanceSource.DECLARED,
        occurred_at=None,
        origin_event_seq=1,
        projector_version=MEMORY_PROJECTOR_VERSION,
    )
    upsert_memory(memory=memory, key_provider=key_provider)  # type: ignore[arg-type]
    return memory


def _row_ids(session: Session, sql: str) -> list[str]:
    """``SELECT <one uuid column> ...`` -> the results as plain strings, explicitly typed
    so mypy doesn't have to infer through ``Session.execute``'s generic-untyped-text overload."""
    result: list[str] = []
    scalars: Sequence[Any] = session.execute(text(sql)).scalars().all()
    for value in scalars:
        result.append(str(value))
    return result


def _seed_decision(*, user: User, key_provider: object) -> None:
    create_decision(
        decision=Decision(
            id=DecisionId(uuid4()),
            user_id=user.id,
            title=f"decision for {user.email}",
            category=DecisionCategory.CAREER,
            context="context",
            options=(DecisionOption(id="a", label="A", body="body"),),
            status=DecisionStatus.DRAFT,
            created_at=datetime.now(UTC),
        ),
        key_provider=key_provider,  # type: ignore[arg-type]
    )


@pytest.mark.usefixtures("configured_engine")
class TestUsersTableIsolation:
    def test_a_user_sees_only_their_own_row(self, key_provider: object) -> None:
        user_a = _make_user(key_provider=key_provider, email=f"rls-a-{uuid4()}@example.test")
        user_b = _make_user(key_provider=key_provider, email=f"rls-b-{uuid4()}@example.test")

        with user_scoped_session(user_a.id) as session:
            rows = _row_ids(session, "SELECT id FROM users")
        assert rows == [str(user_a.id)]

        with user_scoped_session(user_b.id) as session:
            rows = _row_ids(session, "SELECT id FROM users")
        assert rows == [str(user_b.id)]

    def test_unset_context_sees_zero_rows(self, key_provider: object) -> None:
        _make_user(key_provider=key_provider, email=f"rls-unset-{uuid4()}@example.test")
        with get_session() as session:
            rows = _row_ids(session, "SELECT id FROM users")
        assert rows == []

    def test_another_users_uuid_does_not_reveal_existence(self, key_provider: object) -> None:
        user_a = _make_user(key_provider=key_provider, email=f"rls-exist-a-{uuid4()}@example.test")
        user_b = _make_user(key_provider=key_provider, email=f"rls-exist-b-{uuid4()}@example.test")
        with user_scoped_session(user_a.id) as session:
            row = session.execute(
                text("SELECT id FROM users WHERE id = :bid"), {"bid": str(user_b.id)}
            ).first()
        assert row is None


@pytest.mark.usefixtures("configured_engine")
class TestMultiTableIsolation:
    """memory_event, memory, decision - at least one row each, two users, isolated."""

    def test_memory_event_isolation(self, key_provider: object) -> None:
        user_a = _make_user(key_provider=key_provider, email=f"multi-a-{uuid4()}@example.test")
        user_b = _make_user(key_provider=key_provider, email=f"multi-b-{uuid4()}@example.test")
        _seed_memory_event(user=user_a, key_provider=key_provider)
        _seed_memory_event(user=user_b, key_provider=key_provider)

        with user_scoped_session(user_a.id) as session:
            rows = _row_ids(session, "SELECT user_id FROM memory_event")
        assert set(rows) == {str(user_a.id)}
        with user_scoped_session(user_b.id) as session:
            rows = _row_ids(session, "SELECT user_id FROM memory_event")
        assert set(rows) == {str(user_b.id)}

    def test_memory_projection_isolation_and_round_trip(self, key_provider: object) -> None:
        user_a = _make_user(key_provider=key_provider, email=f"multi-mem-a-{uuid4()}@example.test")
        user_b = _make_user(key_provider=key_provider, email=f"multi-mem-b-{uuid4()}@example.test")
        memory_a = _seed_memory(user=user_a, key_provider=key_provider)
        _seed_memory(user=user_b, key_provider=key_provider)

        with user_scoped_session(user_a.id) as session:
            rows = _row_ids(session, "SELECT user_id FROM memory")
        assert set(rows) == {str(user_a.id)}

        visible = list_memories(user_a.id, key_provider=key_provider)  # type: ignore[arg-type]
        assert [m.id for m, _created_at in visible] == [memory_a.id]
        assert visible[0][0].content == memory_a.content

        fetched = get_memory(user_a.id, memory_a.id, key_provider=key_provider)  # type: ignore[arg-type]
        assert fetched is not None
        assert fetched[0] == memory_a

        # User B cannot fetch A's memory even by its exact id (RLS, not a query filter).
        assert get_memory(user_b.id, memory_a.id, key_provider=key_provider) is None  # type: ignore[arg-type]

    def test_decision_isolation(self, key_provider: object) -> None:
        user_a = _make_user(key_provider=key_provider, email=f"multi-dec-a-{uuid4()}@example.test")
        user_b = _make_user(key_provider=key_provider, email=f"multi-dec-b-{uuid4()}@example.test")
        _seed_decision(user=user_a, key_provider=key_provider)
        _seed_decision(user=user_b, key_provider=key_provider)

        with user_scoped_session(user_a.id) as session:
            rows = _row_ids(session, "SELECT user_id FROM decision")
        assert set(rows) == {str(user_a.id)}


class TestPoolingDoesNotLeakTenantContext:
    def test_reused_pooled_connection_does_not_see_prior_users_rows(
        self, app_database_url: str, key_provider: object
    ) -> None:
        """Force a pool of exactly one connection.

        Transaction A sets ``app.user_id``, commits and releases; transaction
        B, on the *same* underlying connection, must start with no tenant
        context at all (s6/s28). Deliberately does not use the shared
        ``configured_engine`` fixture - this test owns its engine's lifecycle
        so it can pin ``pool_size=1``.
        """
        db_session.configure_engine(app_database_url, pool_size=1, max_overflow=0)
        try:
            user_a = _make_user(key_provider=key_provider, email=f"pool-a-{uuid4()}@example.test")
            user_b = _make_user(key_provider=key_provider, email=f"pool-b-{uuid4()}@example.test")

            with user_scoped_session(user_a.id) as session:
                assert _row_ids(session, "SELECT id FROM users")

            # Same pool, same (only) connection - a fresh transaction scoped to B.
            with user_scoped_session(user_b.id) as session:
                rows = set(_row_ids(session, "SELECT id FROM users"))
            assert rows == {str(user_b.id)}
            assert str(user_a.id) not in rows

            # An unscoped session on that same connection inherits nothing.
            with get_session() as session:
                assert _row_ids(session, "SELECT id FROM users") == []
        finally:
            db_session.reset_engine_for_tests()
