"""Closed vocabularies from the Phase-0 specs.

Every value here is a value MINDTRACE reasons about categorically. They are real
enums, never bare strings (Invariant C). ``StrEnum`` keeps serialisation and
YAML/JSON round-tripping trivial while preserving type safety.

Only vocabularies that the specs pin down and that M1-M4 need are defined. Enums
for concepts with no consumer yet (decision category, contradiction kind) are
deferred to the milestone that introduces them. ``MemoryEventType`` lives in
``mindtrace.events.types``, not here (``docs/architecture/01-repository-structure.md``
s3: event-sourcing vocabulary belongs to the ``events`` layer).
"""

from __future__ import annotations

from enum import StrEnum


class EpistemicState(StrEnum):
    """The four states any fact the system holds about a user can be in.

    ``UNCERTAIN`` is a first-class outcome, not an error: the system prefers it
    to a guess (principle 16). Do not collapse these into a generic string.
    """

    DECLARED = "declared"
    OBSERVED = "observed"
    INFERRED = "inferred"
    UNCERTAIN = "uncertain"


class ProvenanceSource(StrEnum):
    """Where a stored datum came from.

    The subset of :class:`EpistemicState` that a concrete memory or evidence row
    can carry. A *source* is never ``uncertain`` -- uncertainty is the absence of
    a belief, not the origin of a datum.
    """

    DECLARED = "declared"
    OBSERVED = "observed"
    INFERRED = "inferred"


class FactorDirection(StrEnum):
    """Whether a higher factor level is better or worse.

    ``BENEFIT``: normalised value = anchor. ``COST``: normalised value = 1 - anchor
    (see ``docs/spec/05-mcda-mathematics.md`` §1c).
    """

    BENEFIT = "benefit"
    COST = "cost"


class ScaleLevel(StrEnum):
    """The shared 5-level ordinal scale for factor levels."""

    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"

    @property
    def rank(self) -> int:
        """0-based position on the scale (``VERY_LOW`` = 0 ... ``VERY_HIGH`` = 4)."""
        return _SCALE_ORDER.index(self)


_SCALE_ORDER: tuple[ScaleLevel, ...] = (
    ScaleLevel.VERY_LOW,
    ScaleLevel.LOW,
    ScaleLevel.MODERATE,
    ScaleLevel.HIGH,
    ScaleLevel.VERY_HIGH,
)

# Short codes used in schema/interview.yaml option profiles.
SCALE_LEVEL_CODES: dict[str, ScaleLevel] = {
    "vl": ScaleLevel.VERY_LOW,
    "l": ScaleLevel.LOW,
    "m": ScaleLevel.MODERATE,
    "h": ScaleLevel.HIGH,
    "vh": ScaleLevel.VERY_HIGH,
}


class SelfReportReliability(StrEnum):
    """How much to trust a user's stated importance for a factor when seeding priors."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FactorTier(StrEnum):
    """Whether a factor participates in v1 aggregation (``CORE``) or is defined but dormant."""

    CORE = "core"
    EXTENDED = "extended"


class PosteriorKind(StrEnum):
    """The posterior family used to represent a trait's uncertainty (ADR-005)."""

    NORMAL = "normal"
    BETA = "beta"


class InterviewItemType(StrEnum):
    """Kinds of Twin Interview item (``docs/spec/07-cold-start-interview.md``)."""

    LIKERT = "likert"
    PAIRWISE = "pairwise"
    GAMBLE = "gamble"
    INTERTEMPORAL = "intertemporal"
    AMBIGUITY = "ambiguity"
    EFFORT = "effort"


class InterviewItemRole(StrEnum):
    """Whether an interview item is scored normally or is a swapped-option consistency check."""

    STANDARD = "standard"
    CONSISTENCY_CHECK = "consistency_check"


class ChoiceOption(StrEnum):
    """Which side of a forced choice an interview answer selects."""

    A = "A"
    B = "B"


class DecisionOutcome(StrEnum):
    """The MCDA decision label. ``UNCERTAIN`` is a real outcome, not a failure."""

    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    UNCERTAIN = "UNCERTAIN"


class UncertainReason(StrEnum):
    """Why a decision resolved to ``UNCERTAIN`` (priority order; ``docs/spec/05`` §5)."""

    SCORE_IN_BAND = "score_in_band"
    INSUFFICIENT_COVERAGE = "insufficient_coverage"
    LOW_MODEL_CONFIDENCE = "low_model_confidence"


class DecisionStatus(StrEnum):
    """Lifecycle of a decision record (``docs/architecture/02-domain-model.md`` AG-5)."""

    DRAFT = "draft"
    SIMULATED = "simulated"
    COMMITTED = "committed"
    ARCHIVED = "archived"


class Polarity(StrEnum):
    """Whether a piece of evidence supports or contradicts a belief."""

    SUPPORT = "support"
    CONTRADICT = "contradict"


class ConsentScope(StrEnum):
    """Consent scopes an inference or LLM call checks before running (ADR-008)."""

    STORE_MEMORIES = "store_memories"
    RUN_INFERENCE = "run_inference"
    USE_LLM_PROVIDER = "use_llm_provider"
    RETAIN_OUTCOMES = "retain_outcomes"


class MemoryType(StrEnum):
    """The kind of thing a projected memory represents (``docs/architecture/02`` AG-3)."""

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PREFERENCE = "preference"
    DECISION = "decision"


class BeliefType(StrEnum):
    """What an :class:`~mindtrace.domain.evidence.Evidence` edge supports (AG-9).

    None of these belief kinds are produced by anything in M2 (no engine
    exists yet to derive a preference, a trait, or a decision factor) - the
    vocabulary is declared now, ahead of its producers, the same way M1
    declared ``DecisionOutcome``/``DecisionStatus`` before the MCDA engine.
    """

    PREFERENCE = "preference"
    TRAIT = "trait"
    VALUE = "value"
    DECISION_FACTOR = "decision_factor"
    CONTRADICTION = "contradiction"


class EvidenceSourceKind(StrEnum):
    """What an :class:`~mindtrace.domain.evidence.Evidence` edge points back to (AG-9)."""

    MEMORY = "memory"
    DECISION = "decision"
    ELICITATION_ANSWER = "elicitation_answer"
    OUTCOME = "outcome"
