"""Unit tests for the M10 cron-stub task functions.

Driven with a plain ``asyncio.run()`` rather than ``pytest-asyncio`` (not a
project dependency) - these coroutines take no fixtures and need no event
loop beyond the call itself.
"""

from __future__ import annotations

import asyncio

from mindtrace.workers.tasks.contradiction_scan import contradiction_scan
from mindtrace.workers.tasks.evolution_snapshot import evolution_snapshot


class TestContradictionScan:
    def test_returns_a_stub_noop_status(self) -> None:
        result = asyncio.run(contradiction_scan({"job_id": "test-job-1"}))
        assert result == {"task": "contradiction_scan", "status": "stub_noop"}

    def test_tolerates_a_missing_job_id(self) -> None:
        """A direct unit call (not through a real arq ``ctx``) must not raise."""
        result = asyncio.run(contradiction_scan({}))
        assert result["status"] == "stub_noop"


class TestEvolutionSnapshot:
    def test_returns_a_stub_noop_status(self) -> None:
        result = asyncio.run(evolution_snapshot({"job_id": "test-job-2"}))
        assert result == {"task": "evolution_snapshot", "status": "stub_noop"}

    def test_tolerates_a_missing_job_id(self) -> None:
        result = asyncio.run(evolution_snapshot({}))
        assert result["status"] == "stub_noop"
