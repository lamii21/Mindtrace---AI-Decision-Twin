"""MINDTRACE observability layer (M9).

Layer 1 (``docs/architecture/01-repository-structure.md`` s3): depends only
on ``mindtrace.domain``. Builds the append-only accountability objects
(``AuditLog``) as pure data - persisting them is a ``db/`` repository's job,
called from ``services/``, exactly like ``security/keyring.py`` builds a key
object without importing ``db/`` itself.
"""

from __future__ import annotations

from mindtrace.observability.audit import build_audit_log

__all__ = ["build_audit_log"]
