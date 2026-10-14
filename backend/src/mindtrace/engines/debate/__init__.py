"""Deterministic ensemble diagnostics and synthesis across parallel twins (M10; ADR-007).

Pure: no persistence, no HTTP, no clock reads, no LLM call. The optional
debate *prose* (``verbalize.py``) is a separate, later-loaded module - the
structured synthesis here never depends on it, and never degrades if it is
unavailable or fails its post-check.
"""

from __future__ import annotations

from mindtrace.engines.debate.disagreement import conflict_axis, label_consensus
from mindtrace.engines.debate.synthesis import BASE_TWIN_VOTE_WEIGHT, SYNTHESIS_VERSION, synthesize

__all__ = [
    "BASE_TWIN_VOTE_WEIGHT",
    "SYNTHESIS_VERSION",
    "conflict_axis",
    "label_consensus",
    "synthesize",
]
