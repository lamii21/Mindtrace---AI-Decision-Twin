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
from sqlalchemy.engine import Engine
from testcontainers.community.postgres import PostgresContainer

from mindtrace.config import get_settings
from mindtrace.db import session as db_session
from tests.integration.conftest import requires_docker
from tests.support.postgres_support import BACKEND_ROOT, INIT_SQL, run_migrations

pytestmark = requires_docker

_TABLES_AT_0001 = {
    "users",
    "user_data_key",
    "consent_record",
    "memory_event",
    "memory",
    "decision",
    "alembic_version",
}
_TABLES_AT_0002 = _TABLES_AT_0001 | {"refresh_token", "idempotency_key"}
_TABLES_AT_0003 = _TABLES_AT_0002 | {"simulation", "prediction", "evidence"}
_TABLES_AT_0004 = _TABLES_AT_0003 | {"twin", "twin_version", "interview_session"}
_TABLES_AT_0005 = _TABLES_AT_0004 | {"audit_log"}

# Used only by the two tests that genuinely reach (and stay at) head -
# `test_0NNN_data_survives_...` tests each reach a specific, earlier
# revision and must not be compared against this (M8 planning: fixed a
# latent fragility where the module-scoped, test-order-dependent shared
# container happened to already sit at head by the time an intermediate
# test's assertion ran).
_EXPECTED_TABLES = _TABLES_AT_0005


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


def _insert_user(engine: Engine, user_id: uuid.UUID) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email, password_hash, status, data_key_ref, "
                "next_event_seq, created_at) VALUES "
                "(:id, :email, 'hash', 'active', 1, 1, now())"
            ),
            {"id": user_id, "email": f"{user_id}@example.dev"},
        )


def _insert_decision_and_simulation(
    engine: Engine, *, user_id: uuid.UUID, decision_id: uuid.UUID, simulation_id: uuid.UUID
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO decision (id, user_id, title, category, context, options, "
                "status, created_at) VALUES "
                "(:id, :user_id, 'x'::bytea, 'career', 'x'::bytea, 'x'::bytea, 'draft', now())"
            ),
            {"id": decision_id, "user_id": user_id},
        )
        conn.execute(
            text(
                "INSERT INTO simulation (id, user_id, decision_id, simulation_version, "
                "scenario_content_hash, extraction, twin_configs, model_confidence, "
                "created_at) VALUES (:id, :user_id, :decision_id, '1', 'hash', "
                "'{}'::jsonb, '[]'::jsonb, '{}'::jsonb, now())"
            ),
            {"id": simulation_id, "user_id": user_id, "decision_id": decision_id},
        )


def _insert_twin(engine: Engine, *, user_id: uuid.UUID, twin_id: uuid.UUID) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO twin (id, user_id, name, next_twin_version, created_at) "
                "VALUES (:id, :user_id, 'Primary', 1, now())"
            ),
            {"id": twin_id, "user_id": user_id},
        )


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
        # Reset to a known-empty state first - `fresh_owner_url` is
        # module-scoped and shared across every test in this file, so this
        # test must not assume what an earlier test left the schema at
        # (M8 planning: fixed a latent order-dependency bug this surfaced).
        command.downgrade(config, "base")
        command.upgrade(config, "0001")

        engine = create_engine(fresh_owner_url)
        user_id = uuid.uuid4()
        try:
            _insert_user(engine, user_id)
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
        assert tables == _TABLES_AT_0002
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
        command.downgrade(config, "base")
        command.upgrade(config, "0002")

        engine = create_engine(fresh_owner_url)
        user_id = uuid.uuid4()
        token_id = uuid.uuid4()
        try:
            _insert_user(engine, user_id)
            with engine.begin() as conn:
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
        assert tables == _TABLES_AT_0003
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


def test_0003_data_survives_upgrade_to_0004_and_downgrade_back_to_0003(
    fresh_owner_url: str,
) -> None:
    """current 0003 -> upgrade 0004 -> verify -> downgrade 0003 -> upgrade 0004.

    Existing 0003-era data (a user + a simulation row) must survive the
    whole round trip - 0004 only adds twin/twin_version/interview_session,
    it never touches 0001-0003's tables (M8 planning s13/s16).
    """
    config = _alembic_config()
    os.environ["MINDTRACE_DATABASE_URL"] = fresh_owner_url
    get_settings.cache_clear()
    try:
        command.downgrade(config, "base")
        command.upgrade(config, "0003")

        engine = create_engine(fresh_owner_url)
        user_id = uuid.uuid4()
        decision_id = uuid.uuid4()
        simulation_id = uuid.uuid4()
        try:
            _insert_user(engine, user_id)
            _insert_decision_and_simulation(
                engine, user_id=user_id, decision_id=decision_id, simulation_id=simulation_id
            )
        finally:
            engine.dispose()

        command.upgrade(config, "0004")
        engine = create_engine(fresh_owner_url)
        try:
            tables = set(inspect(engine).get_table_names())
            with engine.connect() as conn:
                survived: str = conn.execute(
                    text("SELECT email FROM users WHERE id = :id"), {"id": user_id}
                ).scalar_one()
                simulation_survived: uuid.UUID = conn.execute(
                    text("SELECT id FROM simulation WHERE id = :id"), {"id": simulation_id}
                ).scalar_one()
        finally:
            engine.dispose()
        assert tables == _TABLES_AT_0004
        assert survived == f"{user_id}@example.dev"
        assert simulation_survived == simulation_id

        command.downgrade(config, "0003")
        engine = create_engine(fresh_owner_url)
        try:
            tables_after_downgrade = set(inspect(engine).get_table_names())
            with engine.connect() as conn:
                still_there: str = conn.execute(
                    text("SELECT email FROM users WHERE id = :id"), {"id": user_id}
                ).scalar_one()
        finally:
            engine.dispose()
        assert "twin" not in tables_after_downgrade
        assert "twin_version" not in tables_after_downgrade
        assert "interview_session" not in tables_after_downgrade
        assert still_there == f"{user_id}@example.dev"

        command.upgrade(config, "0004")
    finally:
        os.environ.pop("MINDTRACE_DATABASE_URL", None)
        get_settings.cache_clear()
        db_session.reset_engine_for_tests()


def test_0004_data_survives_upgrade_to_0005_and_downgrade_back_to_0004(
    fresh_owner_url: str,
) -> None:
    """current 0004 -> upgrade 0005 -> verify -> downgrade 0004 -> upgrade 0005.

    Existing 0004-era data (a user + a twin row) must survive the whole
    round trip - 0005 only adds ``audit_log``, it never touches 0001-0004's
    tables (M9 planning).
    """
    config = _alembic_config()
    os.environ["MINDTRACE_DATABASE_URL"] = fresh_owner_url
    get_settings.cache_clear()
    try:
        command.downgrade(config, "base")
        command.upgrade(config, "0004")

        engine = create_engine(fresh_owner_url)
        user_id = uuid.uuid4()
        twin_id = uuid.uuid4()
        try:
            _insert_user(engine, user_id)
            _insert_twin(engine, user_id=user_id, twin_id=twin_id)
        finally:
            engine.dispose()

        command.upgrade(config, "0005")
        engine = create_engine(fresh_owner_url)
        try:
            tables = set(inspect(engine).get_table_names())
            with engine.connect() as conn:
                survived: str = conn.execute(
                    text("SELECT email FROM users WHERE id = :id"), {"id": user_id}
                ).scalar_one()
                twin_survived: uuid.UUID = conn.execute(
                    text("SELECT id FROM twin WHERE id = :id"), {"id": twin_id}
                ).scalar_one()
        finally:
            engine.dispose()
        assert tables == _TABLES_AT_0005
        assert survived == f"{user_id}@example.dev"
        assert twin_survived == twin_id

        command.downgrade(config, "0004")
        engine = create_engine(fresh_owner_url)
        try:
            tables_after_downgrade = set(inspect(engine).get_table_names())
            with engine.connect() as conn:
                still_there: str = conn.execute(
                    text("SELECT email FROM users WHERE id = :id"), {"id": user_id}
                ).scalar_one()
        finally:
            engine.dispose()
        assert "audit_log" not in tables_after_downgrade
        assert still_there == f"{user_id}@example.dev"

        command.upgrade(config, "0005")
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
