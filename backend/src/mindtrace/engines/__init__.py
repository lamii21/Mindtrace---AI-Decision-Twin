"""MINDTRACE deterministic decision engines.

Layer 1 of the architecture (``docs/architecture/01-repository-structure.md``):
pure calculations over ``mindtrace.domain`` types. No FastAPI, no SQLAlchemy, no
LLM provider SDK, no persistence, no I/O of any kind -- enforced by
``backend/.importlinter`` and ``tests/unit/test_import_isolation.py``. An
engine's input is always given explicitly by its caller; nothing under this
package queries a database, calls an LLM, or reads memories itself
(``docs/PHASE-0-REVIEW.md`` s5, ADR-002 s16).
"""

from __future__ import annotations
