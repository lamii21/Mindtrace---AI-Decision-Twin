"""Unit test for the worker process entry point.

``main()`` runs a real arq worker forever when called for real, so this
mocks only ``arq.run_worker`` itself (never anything of ours) to prove the
one fact that matters: ``main()`` hands it ``WorkerSettings``, nothing else.
"""

from __future__ import annotations

from unittest.mock import patch

from mindtrace.workers.main import main
from mindtrace.workers.settings import WorkerSettings


def test_main_runs_the_worker_with_worker_settings() -> None:
    with patch("mindtrace.workers.main.run_worker") as mock_run_worker:
        main()
    mock_run_worker.assert_called_once_with(WorkerSettings)
