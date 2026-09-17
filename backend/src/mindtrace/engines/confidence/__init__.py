"""The confidence engine: a deterministic, computed `C`, separate from MCDA's `S`.

Pure, composable, versioned - see ``docs/spec/06-confidence-model.md`` and
``compute.py``'s module docstring for what "composable" excludes (wiring `C`
into a final decision label).
"""

from __future__ import annotations

from mindtrace.engines.confidence.compute import (
    compute_confidence,
    confidence_uncertain_reason,
    is_low_confidence,
)
from mindtrace.engines.confidence.config import (
    DEFAULT_CONFIDENCE_CONFIG,
    ENGINE_VERSION,
    ConfidenceConfig,
    RecalibrationParams,
)
from mindtrace.engines.confidence.errors import ConfidenceValidationError

__all__ = [
    "DEFAULT_CONFIDENCE_CONFIG",
    "ENGINE_VERSION",
    "ConfidenceConfig",
    "ConfidenceValidationError",
    "RecalibrationParams",
    "compute_confidence",
    "confidence_uncertain_reason",
    "is_low_confidence",
]
