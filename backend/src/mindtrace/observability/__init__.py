"""MINDTRACE observability layer (M9 audit; M10 adds structured logging + tracing).

Layer 1 (``docs/architecture/01-repository-structure.md`` s3): depends only
on ``mindtrace.domain`` (plus the focused, observability-only third-party
libraries ``structlog``/``opentelemetry.*`` - the same pattern ``db/``
reserves for ``sqlalchemy`` and ``security/`` for ``cryptography``).
``build_audit_log`` builds the append-only accountability object
(``AuditLog``) as pure data - persisting it is a ``db/`` repository's job,
called from ``services/``. ``get_logger``/``traced_span`` are the only
logging/tracing entry points the rest of the codebase should use - never a
bare ``print`` or a direct ``structlog``/``opentelemetry`` import outside
this package.
"""

from __future__ import annotations

from mindtrace.observability.audit import build_audit_log
from mindtrace.observability.logging import configure_logging, get_logger
from mindtrace.observability.tracing import configure_tracing, traced_span

__all__ = [
    "build_audit_log",
    "configure_logging",
    "configure_tracing",
    "get_logger",
    "traced_span",
]
