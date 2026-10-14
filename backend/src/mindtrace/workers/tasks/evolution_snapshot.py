"""Evolution-snapshot cron stub (M10).

The Evolution Engine itself (belief-delta classification + a timeline API)
is explicitly Phase 2+ ("After M10" in ``docs/11-roadmap-milestones.md``) -
no authoritative snapshot/classification mathematics exists yet for this
task to run, so it performs none. See ``contradiction_scan.py``'s module
docstring - the same reasoning applies here verbatim.
"""

from __future__ import annotations

from typing import Any

from mindtrace.observability import get_logger, traced_span

_logger = get_logger(__name__)

TASK_NAME = "evolution_snapshot"


async def evolution_snapshot(ctx: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, str]:
    """A no-op, observable placeholder - see module docstring for why.

    ``*args``/``**kwargs`` only exist to satisfy ``arq.typing.WorkerCoroutine``'s
    protocol shape - the cron schedule in ``workers/settings.py`` calls this
    with no extra arguments.
    """
    job_id = ctx.get("job_id")
    with traced_span("m10.worker.evolution_snapshot", job_id=str(job_id)):
        _logger.info("m10_worker_started", task=TASK_NAME, job_id=str(job_id))
        result = {"task": TASK_NAME, "status": "stub_noop"}
        _logger.info(
            "m10_worker_completed", task=TASK_NAME, job_id=str(job_id), status=result["status"]
        )
    return result
