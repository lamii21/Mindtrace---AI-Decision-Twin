"""The ``arq`` worker skeleton (M10).

Layer: depends only on ``mindtrace.observability``/``mindtrace.config`` (+
``arq``/``redis``, confined here exactly as ``sqlalchemy`` is confined to
``db/`` and ``cryptography`` to ``security/``) - never ``mindtrace.db``,
``mindtrace.engines``, ``mindtrace.llm``, ``mindtrace.orchestration``, or
``mindtrace.api`` directly (``docs/11-roadmap-milestones.md`` M10: "Workers
are execution infrastructure, not a second business-logic layer").

Both scheduled tasks here (``contradiction_scan``, ``evolution_snapshot``)
are intentionally no-op placeholders: the Contradiction Engine and Evolution
Engine are explicitly listed as Phase 2+ ("After M10") in the roadmap, so
there is no authoritative mathematics yet for either task to run. This
package proves the *worker process itself* - scheduling, execution, job
state, retries - end-to-end, without inventing that future math ahead of
its own milestone. When a later phase defines real contradiction/evolution
detection, its task function will call into a ``services/`` function (the
"worker -> service -> orchestration -> engines" composition the roadmap
describes) - at that point this package's import-linter contract will need
a documented, additive exception, the same way ``services-is-contained``
already has one for ``db``/``orchestration``.
"""

from __future__ import annotations
