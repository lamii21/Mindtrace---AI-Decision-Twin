"""Contradiction-scan cron stub (M10).

The Contradiction Engine itself (detecting conflicting beliefs across a
user's memory graph) is explicitly Phase 2+ ("After M10" in
``docs/11-roadmap-milestones.md``) - no authoritative detection mathematics
exists yet for this task to run, so it performs none. It exists to prove
the worker harness schedules and executes a real job end to end (the
roadmap's own M10 acceptance: "the worker process starts and executes a
scheduled stub"), observably, via ``mindtrace.observability`` - never a bare
``print()`` - and nothing else. It reads/writes nothing; there is no domain
event here to duplicate on retry.
"""

from __future__ import annotations

from typing import Any

from mindtrace.observability import get_logger, traced_span

_logger = get_logger(__name__)

TASK_NAME = "contradiction_scan"


async def contradiction_scan(ctx: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, str]:
    """A no-op, observable placeholder - see module docstring for why.

    ``*args``/``**kwargs`` only exist to satisfy ``arq.typing.WorkerCoroutine``'s
    protocol shape - the cron schedule in ``workers/settings.py`` calls this
    with no extra arguments.
    """
    job_id = ctx.get("job_id")
    with traced_span("m10.worker.contradiction_scan", job_id=str(job_id)):
        _logger.info("m10_worker_started", task=TASK_NAME, job_id=str(job_id))
        result = {"task": TASK_NAME, "status": "stub_noop"}
        _logger.info(
            "m10_worker_completed", task=TASK_NAME, job_id=str(job_id), status=result["status"]
        )
    return result
