"""Mapping a stored source to the epistemic state a UI would render it as.

``Memory.source`` (:class:`~mindtrace.domain.enums.ProvenanceSource`) never
carries ``UNCERTAIN`` - a source describes where a *recorded* datum came from,
and uncertainty is the absence of one, not a kind of origin
(``mindtrace.domain.enums`` module docstring). This module is the one place
that bridges the two: a pure, deterministic, table-driven mapping with no
inference and no LLM (M2 s18) - exactly the information
``docs/PHASE-0-REVIEW.md`` s8 asks M2 to preserve so a future UI can render
solid/dashed/uncertain without this milestone pretending to know more than it
does.
"""

from __future__ import annotations

from mindtrace.domain.enums import EpistemicState, ProvenanceSource

_SOURCE_TO_STATE: dict[ProvenanceSource, EpistemicState] = {
    ProvenanceSource.DECLARED: EpistemicState.DECLARED,
    ProvenanceSource.OBSERVED: EpistemicState.OBSERVED,
    ProvenanceSource.INFERRED: EpistemicState.INFERRED,
}


def classify_epistemic_state(source: ProvenanceSource | None) -> EpistemicState:
    """Map a recorded source to the epistemic state a UI would render.

    ``source is None`` means nothing was found for the query in question (e.g.
    a belief with no evidence, or a memory reference that does not resolve) -
    that is exactly what ``UNCERTAIN`` means (principle 16): the honest
    response is "I don't have enough to say", not a guess.
    """
    if source is None:
        return EpistemicState.UNCERTAIN
    return _SOURCE_TO_STATE[source]
