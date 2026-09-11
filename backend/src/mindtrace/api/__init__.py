"""HTTP layer (FastAPI). Layer 3 of the architecture.

M1 exposes only ``GET /health``. Authentication, persistence, the LLM boundary,
and every business route arrive in later milestones -- a missing feature stays
missing rather than being stubbed to look functional.
"""

from __future__ import annotations

from mindtrace.api.app import create_app

__all__ = ["create_app"]
