"""Engine/session factory and the PostgreSQL tenant-context boundary (ADR-008).

Two ways to get a session, deliberately not interchangeable:

- :func:`get_session` - a bare session with **no** ``app.user_id`` set. RLS
  (``migrations/0001_initial.py``) means this sees zero rows on every
  RLS-protected table by default - there is no session-layer "bypass RLS"
  primitive at all, so "privileged" here means only "capable of touching
  schema-level things", never "sees other users' data". Alembic uses its own
  connection, not this factory; nothing in this milestone's application code
  path actually needs a bare session, but the primitive exists because a
  future cross-tenant-blind operation (a health check, a metrics query)
  should reach for this rather than inventing a bypass.
- :func:`user_scoped_session` - opens a transaction and sets
  ``app.user_id`` via ``SELECT set_config('app.user_id', :uid, true)``
  *inside that transaction*, using a bound parameter (never string
  interpolation). ``set_config``'s third argument, ``is_local=true``, is
  the ``SET LOCAL`` behaviour: the setting reverts automatically at
  transaction end, so a pooled connection handed to a different transaction
  next can never inherit this one's tenant identity (the pooling-leakage
  concern this module exists to prevent).

Every repository/event-store call in ``db/`` takes a session from one of
these two functions - never constructs its own engine or connection.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from mindtrace.domain.ids import UserId


class _EngineRegistry:
    """The process-wide engine/session-factory singleton.

    A small mutable container rather than bare module globals: the same
    effect, without a ``global`` statement at every mutation site.
    """

    engine: Engine | None = None
    session_factory: sessionmaker[Session] | None = None


_registry = _EngineRegistry()


def configure_engine(database_url: str, *, echo: bool = False, **engine_kwargs: object) -> Engine:
    """(Re)configure the process-wide engine/session factory.

    Call sites (test fixtures, a future application startup hook) call this
    once, explicitly, with a real URL - importing this module never connects
    to a database on its own (M6-Persistence planning s4). ``**engine_kwargs``
    passes through to ``create_engine`` (e.g. ``pool_size=1`` for a test that
    must force two sessions to reuse the same pooled connection).
    """
    _registry.engine = create_engine(database_url, echo=echo, pool_pre_ping=True, **engine_kwargs)
    _registry.session_factory = sessionmaker(bind=_registry.engine, expire_on_commit=False)
    return _registry.engine


def get_engine() -> Engine:
    """Return the configured engine.

    Raises:
        RuntimeError: :func:`configure_engine` has not been called yet.
    """
    if _registry.engine is None:
        msg = "db.session.configure_engine() has not been called"
        raise RuntimeError(msg)
    return _registry.engine


def _factory() -> sessionmaker[Session]:
    if _registry.session_factory is None:
        msg = "db.session.configure_engine() has not been called"
        raise RuntimeError(msg)
    return _registry.session_factory


@contextmanager
def get_session() -> Iterator[Session]:
    """A bare session/transaction with no tenant context set. See module docstring."""
    session = _factory()()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def user_scoped_session(user_id: UserId) -> Iterator[Session]:
    """A transaction with ``app.user_id`` set to ``user_id`` for its entire duration.

    ``SET LOCAL`` (via ``set_config(..., is_local=true)``) is transaction-
    scoped, not connection-scoped: it is guaranteed to revert when this
    transaction ends (commit, rollback, or the connection returning to the
    pool), so a later transaction on the same pooled connection starts with
    no tenant context at all - never a leaked identity from a prior user.
    """
    session = _factory()()
    try:
        session.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(user_id)})
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine_for_tests() -> None:
    """Dispose the configured engine and clear it - test teardown only."""
    if _registry.engine is not None:
        _registry.engine.dispose()
    _registry.engine = None
    _registry.session_factory = None
