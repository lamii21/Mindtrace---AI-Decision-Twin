"""Real-PostgreSQL fixtures for ``tests/integration/`` only.

Nothing outside this directory imports ``testcontainers``/``docker`` - unit
tests never require the container runtime (M6-Persistence/Foundation
planning s24). Every fixture here that needs a live container is guarded by
:func:`~tests.support.postgres_support.docker_available` and skips with an
explicit reason when it is not - never silently substitutes SQLite or an
in-memory store and calls the result a passed integration test.
"""

from __future__ import annotations

import base64
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from mindtrace.api import deps as api_deps
from mindtrace.api.app import create_app
from mindtrace.config import get_settings
from mindtrace.db import session as db_session
from mindtrace.security.keyring import EnvironmentKeyProvider
from tests.support.postgres_support import (
    app_role_url,
    docker_available,
    generate_master_key_b64,
    run_migrations,
)

DOCKER_AVAILABLE = docker_available()

requires_docker = pytest.mark.skipif(
    not DOCKER_AVAILABLE,
    reason="Docker/testcontainers unavailable in this environment - integration environment "
    "unavailable, not an implementation failure (M6-Persistence/Foundation planning s24/s30)",
)


@pytest.fixture(scope="session")
def postgres_owner_url() -> Iterator[str]:
    """Start one PostgreSQL 16 (+pgvector) container for the whole integration session.

    Mounts the real ``infra/postgres/init.sql`` so the ``mindtrace_app`` role
    exists exactly as it would in dev/CI, then applies every migration once.
    Yields the *owner* (superuser) connection URL - individual tests get the
    limited ``mindtrace_app`` URL from :func:`app_database_url` instead.
    """
    if not DOCKER_AVAILABLE:
        pytest.skip("Docker/testcontainers unavailable in this environment")

    from testcontainers.community.postgres import PostgresContainer  # noqa: PLC0415

    from tests.support.postgres_support import INIT_SQL  # noqa: PLC0415

    container = PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="mindtrace",
        password="mindtrace",
        dbname="mindtrace",
        driver="psycopg",
    )
    # Must be configured *before* the container starts (`with`/`.start()`) -
    # a volume mapping added afterwards has no effect on an already-running
    # container.
    container.with_volume_mapping(str(INIT_SQL), "/docker-entrypoint-initdb.d/init.sql", "ro")
    with container:
        owner_url = container.get_connection_url()
        run_migrations(owner_url)
        yield owner_url


@pytest.fixture(scope="session")
def app_database_url(postgres_owner_url: str) -> str:
    """The ``mindtrace_app`` role's connection URL - the *realistic* application role.

    Tests must use this, not ``postgres_owner_url``, for anything asserting
    RLS/append-only behaviour: the table owner bypasses neither by default,
    but ``FORCE ROW LEVEL SECURITY`` (``migrations/0001_initial.py``) is the
    real control, and only exercising it via a genuine non-owner role proves
    it (M6-Persistence/Foundation planning s20).
    """
    return app_role_url(postgres_owner_url)


@pytest.fixture
def configured_engine(app_database_url: str) -> Iterator[None]:
    """Point ``db.session`` at the running container's ``mindtrace_app`` role for one test."""
    db_session.configure_engine(app_database_url)
    try:
        yield
    finally:
        db_session.reset_engine_for_tests()


@pytest.fixture
def master_key_b64() -> str:
    """A fresh, random master key for one test - never a fixed/shared secret across tests."""
    return generate_master_key_b64()


@pytest.fixture
def key_provider(master_key_b64: str) -> EnvironmentKeyProvider:
    """A real :class:`EnvironmentKeyProvider` bound to :func:`master_key_b64`."""
    return EnvironmentKeyProvider(base64.b64decode(master_key_b64))


@pytest.fixture
def api_client(
    app_database_url: str, master_key_b64: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """A ``TestClient`` for the real FastAPI app, wired to the running container.

    Env vars are set via ``monkeypatch`` (auto-reverted) and ``Settings``'s
    cache is cleared both before and after, so this test's configuration
    never leaks into a later test's ``get_settings()`` call.
    """
    monkeypatch.setenv("MINDTRACE_DATABASE_URL", app_database_url)
    monkeypatch.setenv("MINDTRACE_MASTER_KEY", master_key_b64)
    monkeypatch.setenv("MINDTRACE_JWT_SECRET", "test-jwt-secret-32-bytes-long!!!")
    get_settings.cache_clear()
    db_session.configure_engine(app_database_url)
    try:
        yield TestClient(create_app())
    finally:
        db_session.reset_engine_for_tests()
        api_deps.reset_key_provider_cache_for_tests()
        get_settings.cache_clear()
