"""Real-PostgreSQL integration-test infrastructure (M6-Persistence/Foundation s24).

Pure helpers, no pytest fixtures here (those live in ``tests/integration/conftest.py``,
scoped to that directory only) - nothing here starts a container at import
time; only *calling* :func:`docker_available`/:func:`run_migrations` does.
This is what keeps unit tests free of any container-runtime dependency, even
though ``sqlalchemy``/``alembic`` (already core dependencies) are imported
at module load.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from mindtrace.config import get_settings
from mindtrace.db import session as db_session

BACKEND_ROOT = Path(__file__).resolve().parents[2]
INIT_SQL = BACKEND_ROOT.parent / "infra" / "postgres" / "init.sql"

APP_ROLE = "mindtrace_app"
APP_ROLE_PASSWORD = "mindtrace_app_dev_only"  # dev/CI-only, matches infra/postgres/init.sql


def docker_available() -> bool:
    """True if a Docker daemon is reachable right now.

    Every integration fixture that needs a real container checks this
    explicitly and skips with a clear reason otherwise - never falls back to
    a fake/in-memory substitute and calls the result a passed integration
    test (M6-Persistence/Foundation planning s24/s30). ``docker`` itself is
    imported lazily here specifically: unlike ``sqlalchemy``/``alembic``
    (core dependencies), it is a dev-only extra, and this function's whole
    purpose is to degrade gracefully when it - or a daemon - is absent.
    """
    try:
        import docker  # type: ignore[import-untyped]  # noqa: PLC0415

        # An explicit, short timeout: an unreachable/misconfigured daemon
        # (a stale named pipe on Windows, a hung TCP endpoint) must fail
        # fast at collection time, never hang the whole test run.
        client = docker.from_env(timeout=3)
        try:
            client.ping()
            return True
        finally:
            client.close()
    except Exception:
        return False


def generate_master_key_b64() -> str:
    """A fresh, random, base64-encoded 32-byte master key for one test run."""
    return base64.b64encode(os.urandom(32)).decode("ascii")


def run_migrations(database_url: str) -> None:
    """Run ``alembic upgrade head`` programmatically against ``database_url``.

    Runs as the migration/owner connection (not ``mindtrace_app``) - schema
    DDL, RLS policy creation, and the app-role GRANTs all need owner
    privileges, matching how ``migrations/0001_initial.py`` itself assumes
    it is *not* running as the limited role it grants to.
    """
    previous = os.environ.get("MINDTRACE_DATABASE_URL")
    os.environ["MINDTRACE_DATABASE_URL"] = database_url
    get_settings.cache_clear()
    try:
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop("MINDTRACE_DATABASE_URL", None)
        else:
            os.environ["MINDTRACE_DATABASE_URL"] = previous
        get_settings.cache_clear()
        db_session.reset_engine_for_tests()


def app_role_url(owner_url: str) -> str:
    """Rewrite an owner/superuser connection URL to authenticate as :data:`APP_ROLE` instead.

    Same host/port/database - only the credentials change, so tests exercise
    the *realistic* application role's grants (and RLS's treatment of a
    non-owner role), never the container's superuser. Uses
    ``render_as_string(hide_password=False)`` deliberately - plain ``str(url)``
    masks the password as ``***``, which would make every connection attempt
    authenticate with the literal string ``"***"`` instead of the real
    credential.
    """
    url = make_url(owner_url).set(username=APP_ROLE, password=APP_ROLE_PASSWORD)
    return url.render_as_string(hide_password=False)
