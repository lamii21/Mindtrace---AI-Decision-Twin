"""The simulation aggregate (``docs/architecture/02-domain-model.md`` AG-7/AG-8).

M7's scope is the roadmap's "base twin only" slice: exactly one
``TwinConfigResult`` (labelled ``"base"``), no parallel twins, no synthesis,
no debate - those are M10. Since M8, ``Prediction.twin_version_id`` is
populated with the exact ``TwinVersion`` used to resolve the posterior - the
cold-start ``initial_posterior(TRAIT_MODEL)`` fallback (``None``) is used
only until the user has a persisted ``Twin``/``TwinVersion``
(``services/decision_service.py``'s posterior-resolution seam).

Both types are tier-B (immutable once written) and hold **only** the
categorical/numeric sub-results M3/M4/M5/M6-A already produced - never the
scenario text itself, never an LLM rationale-span excerpt. See
``services/decision_service.py``'s ``simulate()`` for exactly what gets
persisted and why (M7 planning s7).

``ExtractionProvenance`` deliberately does not import
``mindtrace.llm.schema.ExtractionMetadata`` - ``domain/`` must depend on
nothing (layer 0; ``llm`` is layer 1, above it - ``.importlinter``'s
``domain-is-pure``). It mirrors that type's field shape one-to-one instead;
``services/decision_service.py`` does the trivial field copy.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from mindtrace.domain.confidence import ConfidenceResult
from mindtrace.domain.decision import Contribution, DecisionResult, FactorVector
from mindtrace.domain.enums import DecisionOutcome, ExtractionFailureType, UncertainReason
from mindtrace.domain.ids import (
    DecisionId,
    FactorId,
    PredictionId,
    SimulationId,
    TwinVersionId,
    UserId,
)
from mindtrace.domain.traits import EffectiveWeightVector

_FrozenModel = ConfigDict(frozen=True, extra="forbid")


class ExtractionProvenance(BaseModel):
    """One extraction call's provenance, mirroring ``llm.schema.ExtractionMetadata``.

    A structural mirror, not a subclass or an import of it - see module
    docstring. Field-for-field identical on purpose, so the service-layer
    copy (``ExtractionProvenance(**metadata.model_dump())``) can never
    silently drift out of sync.
    """

    model_config = _FrozenModel

    factor_schema_version: int
    extraction_schema_version: str
    prompt_version: str
    provider: str
    model: str
    mode: str  # "single" | "self_consistency" (ExtractionMode's value)
    temperature: float


class SimulationExtraction(BaseModel):
    """The extraction provenance a ``Simulation`` persists.

    Deliberately narrower than :class:`~mindtrace.llm.schema.ExtractionOutcome`:
    ``rationale_spans`` and ``failure_detail`` are excluded because both can
    carry literal excerpts of the user's scenario text (M7 planning s7).
    """

    model_config = _FrozenModel

    status: str  # "success" | "failed"
    factors: FactorVector
    metadata: ExtractionProvenance
    failure_type: ExtractionFailureType | None
    agreement: dict[FactorId, float] | None


class TwinConfigResult(BaseModel):
    """One twin's run inside a ``Simulation`` - always exactly one, labelled ``"base"``, in M7."""

    model_config = _FrozenModel

    twin: str
    preference: EffectiveWeightVector
    decision: DecisionResult


class Simulation(BaseModel):
    """One complete, immutable, auditable simulation run (AG-7)."""

    model_config = _FrozenModel

    id: SimulationId
    user_id: UserId
    decision_id: DecisionId
    simulation_version: str
    scenario_content_hash: str
    extraction: SimulationExtraction
    twin_configs: tuple[TwinConfigResult, ...]
    model_confidence: ConfidenceResult
    created_at: datetime


class Prediction(BaseModel):
    """The immutable row the Evaluation Engine (M9) will score (AG-8).

    ``predicted_decision`` is the **confidence-gated, product-level** label -
    composed here (``decision_service.simulate()``), never inside
    ``engines.mcda``/``engines.confidence`` themselves: if
    ``confidence_uncertain_reason`` fires, the label is forced to
    ``UNCERTAIN`` with that reason even when the raw MCDA label was
    ``ACCEPT``/``REJECT``. ``predicted_confidence`` is ``confidence.value``,
    persisted as its own independent field - never folded into the label
    choice's numeric value (M7 planning s4/s13). ``twin_version_id`` is the
    exact, immutable ``TwinVersion`` the posterior came from - ``None`` only
    for the cold-start fallback (no ``Twin``/``TwinVersion`` exists yet for
    this user). Set once, at creation, and never re-resolved: a later
    interview round must never change what an existing ``Prediction`` means
    (M8 planning s12).
    """

    model_config = _FrozenModel

    id: PredictionId
    decision_id: DecisionId
    simulation_id: SimulationId
    twin_version_id: TwinVersionId | None
    predicted_decision: DecisionOutcome
    uncertain_reason: UncertainReason | None
    predicted_confidence: float
    credible_interval: None
    factor_contributions: tuple[Contribution, ...]
    margin: float
    engine_version: str
    created_at: datetime


__all__ = [
    "ExtractionProvenance",
    "Prediction",
    "Simulation",
    "SimulationExtraction",
    "TwinConfigResult",
]
