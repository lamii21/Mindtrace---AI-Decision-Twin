"""Append-only enforcement below Python (M6-Persistence/Foundation planning s21).

Both `UPDATE` and `DELETE` are attempted directly with the application role -
ORM method absence is not the control being tested, the PostgreSQL grant is.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from mindtrace.db.event_store import PostgresEventStore
from mindtrace.db.repositories.consent_repository import append_consent
from mindtrace.db.repositories.user_repository import create_user
from mindtrace.db.session import user_scoped_session
from mindtrace.domain.consent import ConsentRecord
from mindtrace.domain.enums import ConsentScope, MemoryType, ProvenanceSource, UserStatus
from mindtrace.domain.ids import ConsentRecordId, UserId
from mindtrace.domain.user import User
from mindtrace.events.types import IngestedPayload
from mindtrace.security.keyring import generate_dek
from tests.integration.conftest import requires_docker

pytestmark = [requires_docker, pytest.mark.usefixtures("configured_engine")]


def _new_user(*, key_provider: object, email: str) -> User:
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


def _seed_one_event(*, key_provider: object) -> User:
    user = _new_user(key_provider=key_provider, email=f"append-only-{uuid4()}@example.test")
    PostgresEventStore(key_provider=key_provider).append(  # type: ignore[arg-type]
        user_id=user.id,
        payload=IngestedPayload(content="immutable", memory_type=MemoryType.EPISODIC),
        source=ProvenanceSource.DECLARED,
        now=datetime.now(UTC),
    )
    return user


class TestMemoryEventIsImmutable:
    def test_application_role_cannot_update_memory_event(self, key_provider: object) -> None:
        user = _seed_one_event(key_provider=key_provider)
        with (
            pytest.raises(DBAPIError, match="permission denied"),
            user_scoped_session(user.id) as session,
        ):
            session.execute(
                text("UPDATE memory_event SET type = 'corrected' WHERE user_id = :uid"),
                {"uid": str(user.id)},
            )

    def test_application_role_cannot_delete_memory_event(self, key_provider: object) -> None:
        user = _seed_one_event(key_provider=key_provider)
        with (
            pytest.raises(DBAPIError, match="permission denied"),
            user_scoped_session(user.id) as session,
        ):
            session.execute(
                text("DELETE FROM memory_event WHERE user_id = :uid"), {"uid": str(user.id)}
            )


class TestConsentRecordIsAppendOnly:
    """AG-1: a change of mind is a new row, never an update (ADR-008 item 8)."""

    def test_application_role_cannot_update_consent_record(self, key_provider: object) -> None:
        user = _new_user(key_provider=key_provider, email=f"consent-ao-{uuid4()}@example.test")
        append_consent(
            ConsentRecord(
                id=ConsentRecordId(uuid4()),
                user_id=user.id,
                scope=ConsentScope.STORE_MEMORIES,
                granted=True,
                policy_version="v1",
                at=datetime.now(UTC),
            )
        )
        with (
            pytest.raises(DBAPIError, match="permission denied"),
            user_scoped_session(user.id) as session,
        ):
            session.execute(
                text("UPDATE consent_record SET granted = false WHERE user_id = :uid"),
                {"uid": str(user.id)},
            )
