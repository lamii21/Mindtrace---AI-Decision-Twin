"""``/v1/elicitation/*`` DTOs (``docs/api/08`` s7, M8).

M8 ships the fixed-order interview only (no Likert warm-up - no
``LikertItem`` domain type exists; see ``engines.elicitation.select_fixed``'s
module docstring for why that is a reported, narrow scope trim, not a gap in
the fixed-order mechanism itself). Consequently:

- ``InterviewItemOut.kind`` never actually takes the value ``"likert"`` in
  M8, though the literal is kept matching the documented contract exactly.
- ``ElicitationAnswer.choice`` is ``Literal["A", "B", "indifferent"]`` only -
  the contract's ``| int`` branch exists solely for likert items, which M8
  never presents.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

_FrozenExtraForbid = ConfigDict(extra="forbid")

InterviewItemKindOut = Literal[
    "likert", "pairwise", "gamble", "intertemporal", "ambiguity", "effort"
]
TraitKindOut = Literal["importance_weight", "disposition"]


class InterviewItemOut(BaseModel):
    """One interview item as presented to the client - never the design vector/profiles."""

    model_config = _FrozenExtraForbid

    item_id: str
    kind: InterviewItemKindOut
    prompt_a: str | None
    prompt_b: str | None
    prompt: str | None


class ElicitationAnswer(BaseModel):
    """``POST /v1/elicitation/sessions/{id}/answers`` request body."""

    model_config = _FrozenExtraForbid

    item_id: str
    choice: Literal["A", "B", "indifferent"]
    latency_ms: int | None = None


class CredibleIntervalOut(BaseModel):
    """A central reporting-scale interval (spec/04 §5)."""

    model_config = _FrozenExtraForbid

    low: float
    high: float


class TraitReportOut(BaseModel):
    """One trait's read-side summary (``docs/api/08`` s6 ``TraitReport``).

    ``trend`` is always ``null`` in M8 - computing it needs the Evolution
    Engine's delta classification (roadmap: "After M10, Phase 2+"), not yet
    built.
    """

    model_config = _FrozenExtraForbid

    id: str
    kind: TraitKindOut
    value: float
    confidence: float
    credible_interval: CredibleIntervalOut
    evidence_count: int
    source: Literal["declared", "inferred"]
    trend: Literal["rising", "falling", "stable"] | None


class InterviewProgressOut(BaseModel):
    """How far through the fixed order a session has gotten."""

    model_config = _FrozenExtraForbid

    answered: int
    target: int


class ElicitationSession(BaseModel):
    """``POST``/``GET /v1/elicitation/sessions[/{id}]`` response body."""

    model_config = _FrozenExtraForbid

    session_id: UUID
    progress: InterviewProgressOut
    next_item: InterviewItemOut | None


class ElicitationStep(BaseModel):
    """``POST /v1/elicitation/sessions/{id}/answers`` response body."""

    model_config = _FrozenExtraForbid

    accepted: bool
    next_item: InterviewItemOut | None
    progress: InterviewProgressOut
    trait_preview: list[TraitReportOut]


class FinalizeResultOut(BaseModel):
    """``POST /v1/elicitation/sessions/{id}:finalize`` response body."""

    model_config = _FrozenExtraForbid

    twin_id: UUID
    twin_version_id: UUID
    interview_noise: float
