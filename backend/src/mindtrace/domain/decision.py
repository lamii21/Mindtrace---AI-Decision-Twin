"""Value types the MCDA engine (``mindtrace.engines.mcda``) consumes and produces.

These are the *inputs a caller supplies explicitly* (spec §00: "the MCDA engine
receives its inputs explicitly") - not something this module derives from
memories, an LLM, or a twin. Nothing here computes anything; construction-time
validation only enforces invariants the mathematics in
``docs/spec/05-mcda-mathematics.md`` already assumes (a weight vector that
doesn't sum to 1 is not "a slightly wrong model", it's not the model spec §2a
describes at all).
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mindtrace.domain.enums import DecisionOutcome, ScaleLevel, UncertainReason
from mindtrace.domain.ids import FactorId

_FrozenModel = ConfigDict(frozen=True, extra="forbid")
_WEIGHT_SUM_TOLERANCE = 1e-6


class FactorReading(BaseModel):
    """One factor's placement for one option: a level, or explicitly "not known".

    ``known=False`` never carries a ``level`` and ``known=True`` always does -
    this is the type-level guard against the "contradictory factor definition"
    case (a level attached to a factor the extractor said it couldn't place).
    """

    model_config = _FrozenModel

    known: bool
    level: ScaleLevel | None = None

    @model_validator(mode="after")
    def _level_matches_known(self) -> FactorReading:
        if self.known and self.level is None:
            msg = "known=True requires a level"
            raise ValueError(msg)
        if not self.known and self.level is not None:
            msg = "known=False must not carry a level"
            raise ValueError(msg)
        return self


class FactorVector(BaseModel):
    """One option's factor readings, keyed by factor id."""

    model_config = _FrozenModel

    readings: dict[FactorId, FactorReading]

    @classmethod
    def from_items(cls, items: Sequence[tuple[FactorId, FactorReading]]) -> FactorVector:
        """Build from a sequence of ``(factor_id, reading)`` pairs, rejecting duplicate ids.

        A plain ``dict`` cannot represent a duplicate key by the time Python
        sees it, so this is the constructor that can actually detect one - the
        shape a caller assembling readings one at a time (e.g. from an
        extractor's per-factor output) would naturally produce.

        Raises:
            ValueError: if the same factor id appears more than once.
        """
        seen: dict[FactorId, FactorReading] = {}
        for factor_id, reading in items:
            if factor_id in seen:
                msg = f"duplicate factor id {factor_id!r}"
                raise ValueError(msg)
            seen[factor_id] = reading
        return cls(readings=seen)

    def known_ids(self) -> tuple[FactorId, ...]:
        """Ids with ``known=True``, sorted for deterministic downstream iteration."""
        return tuple(sorted(fid for fid, reading in self.readings.items() if reading.known))


class DispositionInputs(BaseModel):
    """The four dispositions that bend factor curves and shift weights (spec §1b/§2b)."""

    model_config = _FrozenModel

    risk_tolerance: float = Field(ge=0.0, le=1.0)
    time_discount: float = Field(ge=0.0, le=1.0)
    ambiguity_aversion: float = Field(ge=0.0, le=1.0)
    effort_tolerance: float = Field(ge=0.0, le=1.0)

    @classmethod
    def neutral(cls) -> DispositionInputs:
        """All dispositions at 0.5: no curve shaping, no weight shift (spec §10 property 8)."""
        return cls(
            risk_tolerance=0.5, time_discount=0.5, ambiguity_aversion=0.5, effort_tolerance=0.5
        )


class WeightVector(BaseModel):
    """The twin's raw importance weights (``w_i^raw``), one per core factor, summing to 1.

    This is spec §2a's ``softmax(theta)`` output - M3 receives it as a given;
    computing it from trait posteriors is a different engine's job (ADR-005).
    """

    model_config = _FrozenModel

    weights: dict[FactorId, float]

    @model_validator(mode="after")
    def _validate(self) -> WeightVector:
        if not self.weights:
            msg = "weights must not be empty"
            raise ValueError(msg)
        for factor_id in sorted(self.weights):
            weight = self.weights[factor_id]
            if weight < 0:
                msg = f"weight for {factor_id!r} is negative: {weight}"
                raise ValueError(msg)
        total = sum(self.weights[factor_id] for factor_id in sorted(self.weights))
        if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
            msg = f"weights must sum to 1.0 (within {_WEIGHT_SUM_TOLERANCE}), got {total}"
            raise ValueError(msg)
        return self


class Contribution(BaseModel):
    """One factor's share of the decision score - the row a trace UI renders."""

    model_config = _FrozenModel

    factor_id: FactorId
    level_a: ScaleLevel
    weight: float
    normalized_value_a: float
    normalized_value_b: float
    raw_contribution: float
    contribution_pct: float


class DecisionResult(BaseModel):
    """The engine's complete, self-contained answer: label, score, and the full trace.

    ``raw_score`` is the pre-clamp value the ``contributions`` sum to exactly
    (spec §6: "Identity (pre-clamp): Sum c_i = S"); ``score`` is the clamped,
    reported value. They differ only when ``V(A) - V(B)`` exceeds +-0.5 in
    magnitude, which cannot happen with the default baseline (spec §4) and is
    exercised only by a property test with an explicit, described ``B``.

    The confidence gate (spec §5's ``C < C_MIN``) is deliberately absent:
    ``C`` does not exist until a later milestone's confidence engine. ``label``
    here reflects only the score-band and coverage gates M3 can compute; a
    later milestone composes ``label`` with a computed confidence via a
    separate, thin step - it does not reopen this result.
    """

    model_config = _FrozenModel

    engine_version: str
    config_version: str
    score: float
    raw_score: float
    raw_label: DecisionOutcome
    label: DecisionOutcome
    uncertain_reason: UncertainReason | None
    coverage: float
    margin: float
    known_factor_count: int
    total_factor_count: int
    contributions: tuple[Contribution, ...]
    selected_option: str | None = None


__all__ = [
    "Contribution",
    "DecisionResult",
    "DispositionInputs",
    "FactorReading",
    "FactorVector",
    "WeightVector",
]
