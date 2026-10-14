"""Structured logging (M10).

``structlog``, configured once per process. Every event name is a stable,
named constant (never an ad-hoc f-string) so a log line's shape never
depends on which values happen to be in it. Never logs sensitive content -
scenario text, decrypted memory/decision prose, dispute reasons, tokens,
passwords, or any decrypted protected payload - only ids, enum values,
counts, and durations.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_state = {"configured": False}


def configure_logging(*, level: int = logging.INFO) -> None:
    """Bind ``structlog`` to stdout as JSON lines. Idempotent - safe to call more than once."""
    if _state["configured"]:
        return
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    _state["configured"] = True


def get_logger(name: str) -> Any:
    """A bound ``structlog`` logger for ``name``. Configures logging on first use if needed."""
    if not _state["configured"]:
        configure_logging()
    return structlog.get_logger(name)


def reset_logging_for_tests() -> None:
    """Undo :func:`configure_logging` - test isolation only, never called in production."""
    _state["configured"] = False


__all__ = ["configure_logging", "get_logger", "reset_logging_for_tests"]
