"""Worker process entry point (M10). Run with ``python -m mindtrace.workers.main``.

Equivalent to ``arq mindtrace.workers.settings.WorkerSettings`` (the ``arq``
console script) - this module exists so ``infra/docker-compose.dev.yml``'s
``worker`` service, and anyone running the worker outside that CLI, has one
obvious command that needs no package-entry-point lookup.
"""

from __future__ import annotations

from arq import run_worker

from mindtrace.workers.settings import WorkerSettings


def main() -> None:
    """Run the arq worker in the foreground until it receives a shutdown signal."""
    run_worker(WorkerSettings)


if __name__ == "__main__":  # pragma: no cover - only true when run as `python -m`, never on import
    main()
