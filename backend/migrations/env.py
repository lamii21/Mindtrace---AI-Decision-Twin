"""Alembic environment.

Reads the database URL from ``Settings``, never a hardcoded connection
string or a value baked into ``alembic.ini`` (M6-Persistence/Foundation
planning s4/s22).
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from mindtrace.config import get_settings
from mindtrace.db.base import Base
from mindtrace.db.models import (  # noqa: F401  (imported for side effect: registers metadata)
    ConsentRecordModel,
    DecisionModel,
    MemoryEventModel,
    MemoryModel,
    UserDataKeyModel,
    UserModel,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    settings = get_settings()
    if settings.database_url is None:
        msg = "MINDTRACE_DATABASE_URL is not set - required to run a migration"
        raise RuntimeError(msg)
    return settings.database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live database connection."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a real, live connection."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
