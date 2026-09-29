"""``/v1/simulate`` + ``/v1/simulations/{id}`` DTOs (``docs/api/08`` s5, M7-scoped).

``docs/api/08``'s documented ``SimulateRequest``/``SimulationOut`` describe
the **full post-M10** contract (``twins``, ``per_twin``, ``synthesis``,
``debate``, ``elicitation_hint``, ``twin_version_id`` all require
Twin/TwinVersion (M8) or parallel twins/debate (M10), both out of scope
here). This module implements the documented subset M7 can honestly
produce:

- ``SimulateRequest`` omits ``twins``/``scenario_id`` - accepting either
  would imply a capability (twin selection, conditional scenarios) M7 does
  not have.
- ``SimulationOut.per_twin`` always has exactly one entry, labelled
  ``"base"``.
- ``synthesis``/``debate``/``elicitation_hint``/``twin_version_id`` are
  always ``null`` - each requires a later milestone.
- ``decision.label``/``uncertain_reason`` are the confidence-gated,
  product-level values (``Prediction.predicted_decision``/
  ``uncertain_reason``); ``decision.score``/``margin``/``coverage`` are M3's
  raw, never-adjusted values (``docs/api/08`` s5's own "score and
  confidence.value ... never wired to the same source" contract test, read
  as the general principle it states).
- ``contributions``/``confidence`` mirror the domain ``Contribution``/
  ``ConfidenceResult`` field names directly rather than inventing a second,
  renamed vocabulary (``signed_pct``/``n_value``/``direction`` in the
  contract doc) the math does not actually need.
- ``trace`` is intentionally shallow (AG-9: "depth is 2-3"): one
  ``decision`` node, one ``factor`` node per known factor, one ``evidence``
  node for the single edge M7 actually writes - never a fabricated
  ``memory`` chain, since no memory-to-preference pipeline exists yet.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

_FrozenExtraForbid = ConfigDict(extra="forbid")

DecisionLabelOut = Literal["ACCEPT", "REJECT", "UNCERTAIN"]
UncertainReasonOut = Literal["score_in_band", "insufficient_coverage", "low_model_confidence"]


class SimulateRequest(BaseModel):
    """``POST /v1/simulate`` request body."""

    model_config = _FrozenExtraForbid

    decision_id: UUID


class ContributionOut(BaseModel):
    """One factor's share of the decision score (mirrors ``domain.decision.Contribution``)."""

    model_config = _FrozenExtraForbid

    factor_id: str
    level_a: str
    weight: float
    normalized_value_a: float
    normalized_value_b: float
    raw_contribution: float
    contribution_pct: float


class ConfidenceInputsOut(BaseModel):
    """Mirrors ``domain.confidence.ConfidenceInputs`` - the full audit trace behind ``C``."""

    model_config = _FrozenExtraForbid

    evidence_sufficiency: float
    n_bar: float
    coverage: float
    ensemble_disagreement: float | None
    ensemble_term_capped: bool
    historical_calibration: float | None
    calibrated: str
    calibration_n: int
    extraction_entropy: float | None
    extraction_path: str
    margin_adequacy: float
    margin: float


class ConfidenceOut(BaseModel):
    """``spec/06 §9`` object, verbatim (``docs/api/08`` s5) - mirrors ``ConfidenceResult``."""

    model_config = _FrozenExtraForbid

    confidence_engine_version: str
    confidence_config_version: str
    value: float
    raw: float
    calibrated_output: bool
    credible_interval: None
    inputs: ConfidenceInputsOut
    weights_used: dict[str, float]


class DecisionSummaryOut(BaseModel):
    """The label the user acts on - confidence-gated.

    ``score``/``margin``/``coverage`` are M3's raw, never-adjusted values.
    """

    model_config = _FrozenExtraForbid

    label: DecisionLabelOut
    uncertain_reason: UncertainReasonOut | None
    score: float
    margin: float
    coverage: float


class TwinResultOut(BaseModel):
    """One twin's result inside ``per_twin`` - always exactly one entry (``"base"``) in M7."""

    model_config = _FrozenExtraForbid

    twin: str
    label: DecisionLabelOut
    score: float
    top_contributions: list[ContributionOut]


class TraceNodeOut(BaseModel):
    """One node in the (intentionally shallow) provenance trace."""

    model_config = _FrozenExtraForbid

    id: str
    kind: Literal["decision", "factor", "evidence"]
    label: str


class TraceEdgeOut(BaseModel):
    """One edge in the provenance trace."""

    model_config = _FrozenExtraForbid

    source: str
    target: str
    kind: Literal["cites", "supports"]


class TraceGraphOut(BaseModel):
    """``decision <- factor <- evidence`` - never a fabricated ``memory`` hop (module docstring)."""

    model_config = _FrozenExtraForbid

    nodes: list[TraceNodeOut]
    edges: list[TraceEdgeOut]


class SimulationOut(BaseModel):
    """``POST /v1/simulate`` / ``GET /v1/simulations/{id}`` response body."""

    model_config = _FrozenExtraForbid

    simulation_id: UUID
    decision_id: UUID
    engine_version: str
    factor_schema_version: int
    twin_version_id: None
    decision: DecisionSummaryOut
    confidence: ConfidenceOut
    contributions: list[ContributionOut]
    trace: TraceGraphOut
    per_twin: list[TwinResultOut]
    synthesis: None
    debate: None
    elicitation_hint: None
    created_at: datetime


# `Page[SimulationSummary]` (`GET /v1/decisions/{id}/simulations`) is documented
# without its own field list separate from `SimulationOut` - same reasoning
# `DecisionSummary = DecisionOut` already uses (M6-API planning).
SimulationSummary = SimulationOut
