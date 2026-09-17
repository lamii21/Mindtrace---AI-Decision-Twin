"""`extraction_entropy` (spec §06 §4.4).

No LLM extraction pipeline exists yet (that is a later milestone's `llm/`
package), so there is no `rationale_span` or self-consistency data to consume.
`signal=None` represents that "unavailable" state explicitly and is kept
distinct from `ExtractionSignal.single()`, which asserts a real extraction
actually ran cleanly - the spec's fixed-default fast path is only valid once
that assertion is true.
"""

from __future__ import annotations

from collections.abc import Mapping

from mindtrace.domain.confidence import ExtractionSignal
from mindtrace.domain.ids import FactorId
from mindtrace.engines.confidence.errors import ConfidenceValidationError

_SINGLE_PATH_ENTROPY = 0.10


def extraction_entropy(
    signal: ExtractionSignal | None,
    known_weights: Mapping[FactorId, float],
) -> tuple[float | None, str]:
    """`(extraction_entropy, extraction_path)` (spec §06 §4.4).

    Raises:
        ConfidenceValidationError: if a `self_consistency` signal's agreement
            map does not cover exactly the decision's known-factor set - a
            missing factor cannot be silently scored as full agreement.
    """
    if signal is None:
        return None, "unavailable"

    if signal.path == "single":
        return _SINGLE_PATH_ENTROPY, "single"

    assert signal.agreement is not None  # ExtractionSignal's own validator guarantees this
    known_ids = set(known_weights)
    agreement_ids = set(signal.agreement)
    if agreement_ids != known_ids:
        missing = sorted(known_ids - agreement_ids)
        extra = sorted(agreement_ids - known_ids)
        msg = (
            "self_consistency agreement must cover exactly the decision's known "
            f"factors; missing={missing}, extra={extra}"
        )
        raise ConfidenceValidationError(msg)

    weighted_agreement = sum(
        known_weights[factor_id] * signal.agreement[factor_id]
        for factor_id in sorted(known_weights)
    )
    return 1.0 - weighted_agreement, "self_consistency"
