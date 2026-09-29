"""Migration reversibility and schema-drift detection.

M6-Persistence/Foundation planning s23. ``postgres_owner_url`` already ran
``upgrade head`` once (session-scoped, in ``conftest.py``); this module
proves the full ``downgrade base`` -> ``upgrade head`` round trip on a
second, independent container so the two don't interfere.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from testcontainers.community.postgres import PostgresContainer

from mindtrace.config import get_settings
from mindtrace.db import session as db_session
from tests.integration.conftest import requires_docker
from tests.support.postgres_support import BACKEND_ROOT, INIT_SQL, run_migrations

pytestmark = requires_docker

_EXPECTED_TABLES = {
    "users",
    "user_data_key",
    "consent_record",
    "memory_event",
    "memory",
    "decision",
    "refresh_token",
    "idempotency_key",
    "simulation",
    "prediction",
    "evidence",
    "alembic_version",
}


@pytest.fixture(scope="module")
def fresh_owner_url() -> Iterator[str]:
    """A second, independent container.

    This module mutates schema state (downgrade/upgrade) and must not
    interfere with the session-scoped fixture other integration modules
    share.
    """
    container = PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="mindtrace",
        password="mindtrace",
        dbname="mindtrace",
        driver="psycopg",
    )
    container.with_volume_mapping(str(INIT_SQL), "/docker-entrypoint-initdb.d/init.sql", "ro")
    with container:
        yield container.get_connection_url()


def _alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return config


def test_upgrade_head_creates_exactly_this_milestones_tables(fresh_owner_url: str) -> None:
    run_migrations(fresh_owner_url)
    engine = create_engine(fresh_owner_url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert tables == _EXPECTED_TABLES


def test_downgrade_base_then_upgrade_head_round_trips_cleanly(fresh_owner_url: str) -> None:
    run_migrations(fresh_owner_url)

    os.environ["MINDTRACE_DATABASE_URL"] = fresh_owner_url
    get_settings.cache_clear()
    try:
        config = _alembic_config()
        command.downgrade(config, "base")

        engine = create_engine(fresh_owner_url)
        try:
            tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
        finally:
            engine.dispose()
        assert tables == set()

        command.upgrade(config, "head")
    finally:
        os.environ.pop("MINDTRACE_DATABASE_URL", None)
        get_settings.cache_clear()
        db_session.reset_engine_for_tests()

    engine = create_engine(fresh_owner_url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert tables == _EXPECTED_TABLES


def test_0001_data_survives_upgrade_to_0002_and_downgrade_back_to_0001(
    fresh_owner_url: str,
) -> None:
    """current 0001 -> upgrade 0002 -> verify -> downgrade 0001 -> upgrade 0002.

    Existing 0001-era data (a user row) must survive the whole round trip -
    0002 only adds new tables/functions, it never touches 0001's (M6-API
    planning s13).
    """
    config = _alembic_config()
    os.environ["MINDTRACE_DATABASE_URL"] = fresh_owner_url
    get_settings.cache_clear()
    try:
        command.upgrade(config, "0001")

        engine = create_engine(fresh_owner_url)
        user_id = uuid.uuid4()
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO users (id, email, password_hash, status, data_key_ref, "
                        "next_event_seq, created_at) VALUES "
                        "(:id, :email, 'hash', 'active', 1, 1, now())"
                    ),
                    {"id": user_id, "email": f"{user_id}@example.dev"},
                )
        finally:
            engine.dispose()

        command.upgrade(config, "0002")
        engine = create_engine(fresh_owner_url)
        try:
            tables = set(inspect(engine).get_table_names())
            with engine.connect() as conn:
                survived: str = conn.execute(
                    text("SELECT email FROM users WHERE id = :id"), {"id": user_id}
                ).scalar_one()
        finally:
            engine.dispose()
        assert tables == _EXPECTED_TABLES
        assert survived == f"{user_id}@example.dev"

        command.downgrade(config, "0001")
        engine = create_engine(fresh_owner_url)
        try:
            tables_after_downgrade = set(inspect(engine).get_table_names())
            with engine.connect() as conn:
                still_there: str = conn.execute(
                    text("SELECT email FROM users WHERE id = :id"), {"id": user_id}
                ).scalar_one()
        finally:
            engine.dispose()
        assert "refresh_token" not in tables_after_downgrade
        assert "idempotency_key" not in tables_after_downgrade
        assert still_there == f"{user_id}@example.dev"

        command.upgrade(config, "0002")
    finally:
        os.environ.pop("MINDTRACE_DATABASE_URL", None)
        get_settings.cache_clear()
        db_session.reset_engine_for_tests()


def test_0002_data_survives_upgrade_to_0003_and_downgrade_back_to_0002(
    fresh_owner_url: str,
) -> None:
    """current 0002 -> upgrade 0003 -> verify -> downgrade 0002 -> upgrade 0003.

    Existing 0002-era data (a user + a refresh_token row) must survive the
    whole round trip - 0003 only adds simulation/prediction/evidence, it
    never touches 0001/0002's tables (M7 planning s5).
    """
    config = _alembic_config()
    os.environ["MINDTRACE_DATABASE_URL"] = fresh_owner_url
    get_settings.cache_clear()
    try:
        command.upgrade(config, "0002")

        engine = create_engine(fresh_owner_url)
        user_id = uuid.uuid4()
        token_id = uuid.uuid4()
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO users (id, email, password_hash, status, data_key_ref, "
                        "next_event_seq, created_at) VALUES "
                        "(:id, :email, 'hash', 'active', 1, 1, now())"
                    ),
                    {"id": user_id, "email": f"{user_id}@example.dev"},
                )
                conn.execute(
                    text(
                        "INSERT INTO refresh_token (id, user_id, family_id, token_hash, "
                        "issued_at, expires_at) VALUES "
                        "(:id, :user_id, :family_id, 'hash', now(), now() + interval '1 day')"
                    ),
                    {"id": token_id, "user_id": user_id, "family_id": uuid.uuid4()},
                )
        finally:
            engine.dispose()

        command.upgrade(config, "0003")
        engine = create_engine(fresh_owner_url)
        try:
            tables = set(inspect(engine).get_table_names())
            with engine.connect() as conn:
                survived: str = conn.execute(
                    text("SELECT email FROM users WHERE id = :id"), {"id": user_id}
                ).scalar_one()
                token_survived: uuid.UUID = conn.execute(
                    text("SELECT id FROM refresh_token WHERE id = :id"), {"id": token_id}
                ).scalar_one()
        finally:
            engine.dispose()
        assert tables == _EXPECTED_TABLES
        assert survived == f"{user_id}@example.dev"
        assert token_survived == token_id

        command.downgrade(config, "0002")
        engine = create_engine(fresh_owner_url)
        try:
            tables_after_downgrade = set(inspect(engine).get_table_names())
            with engine.connect() as conn:
                still_there: str = conn.execute(
                    text("SELECT email FROM users WHERE id = :id"), {"id": user_id}
                ).scalar_one()
        finally:
            engine.dispose()
        assert "simulation" not in tables_after_downgrade
        assert "prediction" not in tables_after_downgrade
        assert "evidence" not in tables_after_downgrade
        assert still_there == f"{user_id}@example.dev"

        command.upgrade(config, "0003")
    finally:
        os.environ.pop("MINDTRACE_DATABASE_URL", None)
        get_settings.cache_clear()
        db_session.reset_engine_for_tests()


def test_rls_is_enabled_and_forced_on_every_user_owned_table(fresh_owner_url: str) -> None:
    run_migrations(fresh_owner_url)
    engine = create_engine(fresh_owner_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE relname = ANY(:names)"
                ),
                {"names": list(_EXPECTED_TABLES - {"alembic_version"})},
            ).all()
    finally:
        engine.dispose()
    assert len(rows) == len(_EXPECTED_TABLES) - 1
    for _name, enabled, forced in rows:
        assert enabled is True
        assert forced is True
