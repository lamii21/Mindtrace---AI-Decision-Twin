"""The ``arq`` ``WorkerSettings`` class (M10).

A plain class with the attributes ``arq.worker.run_worker``/the ``arq`` CLI
read by name (``functions``, ``cron_jobs``, ``redis_settings``, ...) - arq
itself defines no base class to inherit from (``arq.typing.
WorkerSettingsBase`` is a ``Protocol``, structural only). Points at
``Settings.redis_url`` (``mindtrace.config`` - the same ``MINDTRACE_``-
prefixed, env-driven settings every other process reads), never a
hard-coded host.

Both cron jobs run once a day, offset by an hour, so they never overlap -
an arbitrary, documented choice (no spec pins an exact schedule for either
stub); ``run_at_startup=False`` so a fresh ``docker compose up`` does not
immediately burn a job run before anything exists for it to look at.
"""

from __future__ import annotations

from collections.abc import Sequence

from arq import cron
from arq.connections import RedisSettings
from arq.cron import CronJob
from arq.typing import StartupShutdown, WorkerCoroutine
from arq.worker import Function

from mindtrace.config import get_settings
from mindtrace.workers.tasks.contradiction_scan import contradiction_scan
from mindtrace.workers.tasks.evolution_snapshot import evolution_snapshot


class WorkerSettings:
    """Registered functions + cron schedule for the ``mindtrace`` arq worker process.

    Every attribute ``arq.typing.WorkerSettingsBase`` declares is annotated
    here with that exact type (not a narrower one mypy would otherwise infer
    from the literal assignment, e.g. plain ``None``) - ``--strict`` checks a
    mutable ``Protocol`` attribute invariantly, so a narrower inferred type
    fails even though it would be a valid runtime value.
    """

    functions: Sequence[WorkerCoroutine | Function] = (contradiction_scan, evolution_snapshot)
    cron_jobs: Sequence[CronJob] | None = (
        cron(contradiction_scan, hour=3, minute=0, run_at_startup=False),
        cron(evolution_snapshot, hour=4, minute=0, run_at_startup=False),
    )
    on_startup: StartupShutdown | None = None
    on_shutdown: StartupShutdown | None = None
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = 3


__all__ = ["WorkerSettings"]
