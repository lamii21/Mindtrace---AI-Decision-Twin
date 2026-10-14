"""Real-Redis integration tests for the M10 arq worker harness.

Never a mocked Redis/worker in place of the real thing - the same rule
``tests/integration/conftest.py`` already states for Postgres
(M6-Persistence/Foundation planning s24/s30), applied to the worker
infrastructure M10 adds.

Every test runs its whole scenario (enqueue, worker, result check) inside
one ``asyncio.run()`` call, constructing one ``arq.worker.Worker`` directly
(``burst=True``, via :meth:`Worker.async_run`, never the synchronous
``Worker.run()``/``run_worker()`` wrapper) over one shared pool - not the
``mindtrace.workers.settings.WorkerSettings`` singleton, since that class
resolves its own ``redis_settings`` from ``get_settings()`` once at import
time and these tests need the per-session container URL instead. This is
deliberate, not just tidier: Windows' ``ProactorEventLoop`` defers a
closed socket's actual teardown to a callback that only runs if its own
loop gets to run again; spreading one scenario across several separate
``asyncio.run()`` calls (each with its own throwaway loop) left sockets
closed-but-not-yet-torn-down when their loop vanished, surfacing later as
spurious ``ResourceWarning``s - this project's ``filterwarnings = ["error",
...]`` (``pyproject.toml``) turns those into test failures.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from arq import create_pool, func
from arq.connections import RedisSettings
from arq.jobs import Job, JobResult
from arq.worker import Retry, Worker

from mindtrace.workers.tasks.contradiction_scan import contradiction_scan
from mindtrace.workers.tasks.evolution_snapshot import evolution_snapshot
from tests.integration.conftest import requires_docker


@pytest.fixture(autouse=True)
def _isolated_redis(redis_url: str) -> Iterator[None]:
    """Flush the shared, session-scoped Redis container before each test.

    ``redis_url`` is one real container for the whole integration session
    (``tests/integration/conftest.py``) - without this, a job one test
    enqueues but never drains (the pre-run idempotency check below enqueues
    on purpose, never runs a worker for it) would sit in the queue and get
    silently picked up by a *later* test's differently-scoped worker.
    """

    async def _flush() -> None:
        pool = await create_pool(RedisSettings.from_dsn(redis_url))
        try:
            await pool.flushdb()
        finally:
            await pool.aclose()

    asyncio.run(_flush())
    yield


async def _enqueue_run_and_get_result(
    redis_settings: RedisSettings,
    functions: tuple[Any, ...],
    function_name: str,
    *,
    job_id: str | None = None,
    max_tries: int = 5,
) -> JobResult | None:
    """Enqueue one job, drain it with one burst-mode worker, return its result.

    One pool, one loop, for the whole scenario - see the module docstring.
    """
    pool = await create_pool(redis_settings)
    try:
        job = await pool.enqueue_job(function_name, _job_id=job_id)
        assert job is not None
        worker = Worker(
            functions, redis_pool=pool, burst=True, poll_delay=0.01, max_tries=max_tries
        )
        await worker.async_run()
        return await Job(job.job_id, pool).result_info()
    finally:
        await pool.aclose()


@requires_docker
class TestWorkerExecutesRealTasks:
    """ "Successful job" - the roadmap's own M10 acceptance: "the worker process
    starts and executes a scheduled stub"."""

    def test_contradiction_scan_runs_to_completion_with_the_expected_result(
        self, redis_url: str
    ) -> None:
        redis_settings = RedisSettings.from_dsn(redis_url)
        info = asyncio.run(
            _enqueue_run_and_get_result(redis_settings, (contradiction_scan,), "contradiction_scan")
        )
        assert info is not None
        assert info.success is True
        assert info.result == {"task": "contradiction_scan", "status": "stub_noop"}

    def test_evolution_snapshot_runs_to_completion_with_the_expected_result(
        self, redis_url: str
    ) -> None:
        redis_settings = RedisSettings.from_dsn(redis_url)
        info = asyncio.run(
            _enqueue_run_and_get_result(redis_settings, (evolution_snapshot,), "evolution_snapshot")
        )
        assert info is not None
        assert info.success is True
        assert info.result == {"task": "evolution_snapshot", "status": "stub_noop"}


@requires_docker
class TestWorkerRetrySemantics:
    """ "Failed job"/"retry" - a locally-defined flaky coroutine, never the real
    (always-succeeding) stub tasks: this is about the worker *harness*'s retry
    behaviour, not production task logic.

    arq only retries a job that explicitly raises ``arq.worker.Retry`` (or is
    cancelled) - an ordinary exception marks the job permanently failed on its
    first try, no automatic retry (confirmed directly against ``arq.worker.
    Worker.run_job``'s source: only ``isinstance(e, Retry)`` re-queues).
    """

    def test_a_job_that_keeps_requesting_retry_is_retried_up_to_max_tries_then_fails(
        self, redis_url: str
    ) -> None:
        attempts: list[int] = []

        async def always_retries(ctx: dict[str, Any]) -> None:
            attempts.append(len(attempts) + 1)
            raise Retry()

        redis_settings = RedisSettings.from_dsn(redis_url)
        info = asyncio.run(
            _enqueue_run_and_get_result(
                redis_settings,
                (func(always_retries, name="always_retries"),),
                "always_retries",
                max_tries=3,
            )
        )

        assert info is not None
        assert info.success is False
        # Ran exactly `max_tries` times - never fewer (silently dropped) and
        # never more (duplicated beyond what the worker was configured to allow).
        assert len(attempts) == 3

    def test_a_job_that_requests_retry_once_then_succeeds_runs_exactly_twice(
        self, redis_url: str
    ) -> None:
        attempts: list[int] = []

        async def retries_once(ctx: dict[str, Any]) -> dict[str, int]:
            attempts.append(len(attempts) + 1)
            if len(attempts) == 1:
                raise Retry()
            return {"try": len(attempts)}

        redis_settings = RedisSettings.from_dsn(redis_url)
        info = asyncio.run(
            _enqueue_run_and_get_result(
                redis_settings,
                (func(retries_once, name="retries_once"),),
                "retries_once",
                max_tries=3,
            )
        )

        assert info is not None
        assert info.success is True
        assert info.result == {"try": 2}
        assert len(attempts) == 2


@requires_docker
class TestIdempotentRetry:
    """A caller retrying its OWN already-submitted job (e.g. an HTTP retry re-sending
    the same ``Idempotency-Key``-derived job id) must never cause the task to run
    twice - arq's own job-id dedup, exercised against the real container rather than
    assumed."""

    def test_resubmitting_the_same_job_id_before_it_runs_enqueues_nothing_new(
        self, redis_url: str
    ) -> None:
        async def _scenario() -> tuple[str | None, str | None]:
            pool = await create_pool(RedisSettings.from_dsn(redis_url))
            try:
                job_id = "m10-idempotent-pre-run"
                first = await pool.enqueue_job("contradiction_scan", _job_id=job_id)
                second = await pool.enqueue_job("contradiction_scan", _job_id=job_id)
                return (
                    first.job_id if first is not None else None,
                    second.job_id if second is not None else None,
                )
            finally:
                await pool.aclose()

        first_id, second_id = asyncio.run(_scenario())
        assert first_id == "m10-idempotent-pre-run"
        assert second_id is None  # arq recognised the duplicate id and enqueued nothing

    def test_resubmitting_the_same_job_id_after_it_completes_does_not_rerun_it(
        self, redis_url: str
    ) -> None:
        attempts: list[int] = []

        async def counting_task(ctx: dict[str, Any]) -> dict[str, int]:
            attempts.append(len(attempts) + 1)
            return {"ran": len(attempts)}

        async def _scenario() -> str | None:
            redis_settings = RedisSettings.from_dsn(redis_url)
            pool = await create_pool(redis_settings)
            try:
                job_id = "m10-idempotent-post-run"
                first = await pool.enqueue_job("counting_task", _job_id=job_id)
                assert first is not None
                worker = Worker(
                    (func(counting_task, name="counting_task"),),
                    redis_pool=pool,
                    burst=True,
                    poll_delay=0.01,
                )
                await worker.async_run()

                second = await pool.enqueue_job("counting_task", _job_id=job_id)
                return second.job_id if second is not None else None
            finally:
                await pool.aclose()

        second_id = asyncio.run(_scenario())
        assert len(attempts) == 1
        assert second_id is None  # the completed job's result is still held - no re-run
