"""Use-case coordination and transaction boundaries (layer 2, M6-API).

``docs/architecture/01-repository-structure.md`` s3: loads inputs via
repositories, calls engines with pure data, persists results, returns domain
objects - never ORM rows, never HTTP concerns. M6 services never call
``mindtrace.orchestration`` (no `/v1/simulate` yet - that is M7) and never
import SQLAlchemy directly (``mindtrace.db.repositories`` owns SQL).
"""

from __future__ import annotations
