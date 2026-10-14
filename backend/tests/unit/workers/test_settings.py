"""Unit tests for ``WorkerSettings`` - never started for real (no live worker, no real
Redis connection attempt), only the class body's own structure."""

from __future__ import annotations

from arq.connections import RedisSettings
from arq.cron import CronJob

from mindtrace.workers.settings import WorkerSettings
from mindtrace.workers.tasks.contradiction_scan import contradiction_scan
from mindtrace.workers.tasks.evolution_snapshot import evolution_snapshot


class TestWorkerSettings:
    def test_registers_exactly_the_two_m10_stub_tasks(self) -> None:
        assert set(WorkerSettings.functions) == {contradiction_scan, evolution_snapshot}

    def test_schedules_a_cron_job_for_each_registered_task(self) -> None:
        assert WorkerSettings.cron_jobs is not None
        assert len(WorkerSettings.cron_jobs) == 2
        assert all(isinstance(job, CronJob) for job in WorkerSettings.cron_jobs)
        scheduled_names = {job.name for job in WorkerSettings.cron_jobs}
        assert scheduled_names == {"cron:contradiction_scan", "cron:evolution_snapshot"}

    def test_redis_settings_is_a_real_redissettings_instance(self) -> None:
        """Structural only - never actually connects (that would need a live Redis)."""
        assert isinstance(WorkerSettings.redis_settings, RedisSettings)

    def test_max_tries_is_a_small_finite_bound(self) -> None:
        assert WorkerSettings.max_tries == 3
