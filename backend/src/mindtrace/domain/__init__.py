"""MINDTRACE domain layer.

Layer 0 of the architecture (``docs/architecture/01-repository-structure.md``):
the shared vocabulary and the canonical schema model. Depends only on the
standard library and pydantic. It must never import ``fastapi``, ``sqlalchemy``,
an LLM provider SDK, or any higher ``mindtrace`` layer -- enforced by
``backend/.importlinter`` and ``tests/unit/test_import_isolation.py``.
"""

from __future__ import annotations

from mindtrace.domain.enums import (
    BeliefType,
    ChoiceOption,
    ConsentScope,
    DecisionOutcome,
    DecisionStatus,
    EpistemicState,
    EvidenceSourceKind,
    FactorDirection,
    FactorTier,
    InterviewItemRole,
    InterviewItemType,
    MemoryType,
    Polarity,
    PosteriorKind,
    ProvenanceSource,
    ScaleLevel,
    SelfReportReliability,
    UncertainReason,
)
from mindtrace.domain.errors import (
    DomainError,
    MindtraceError,
    SchemaConsistencyError,
    SchemaError,
    SchemaStructureError,
    SchemaValidationError,
)
from mindtrace.domain.evidence import Evidence
from mindtrace.domain.factors import (
    FactorSpec,
    FactorTaxonomy,
    OrdinalScale,
    load_factor_taxonomy,
    parse_factor_taxonomy,
)
from mindtrace.domain.ids import (
    DispositionId,
    EventId,
    EvidenceId,
    EvidenceTag,
    FactorId,
    InterviewItemId,
    MemoryId,
    UserId,
)
from mindtrace.domain.interview import (
    DispositionItem,
    InterviewBank,
    InterviewConfig,
    PairwiseItem,
    load_interview_bank,
    parse_interview_bank,
)
from mindtrace.domain.memory import Memory
from mindtrace.domain.provenance import classify_epistemic_state
from mindtrace.domain.schema_bundle import SchemaBundle, load_schema_bundle
from mindtrace.domain.traits import (
    BetaPrior,
    DispositionSpec,
    ImportanceWeightSpec,
    NormalPrior,
    ReportConfig,
    TraitModel,
    load_trait_model,
    parse_trait_model,
)

__all__ = [
    "BeliefType",
    "BetaPrior",
    "ChoiceOption",
    "ConsentScope",
    "DecisionOutcome",
    "DecisionStatus",
    "DispositionId",
    "DispositionItem",
    "DispositionSpec",
    "DomainError",
    "EpistemicState",
    "EventId",
    "Evidence",
    "EvidenceId",
    "EvidenceSourceKind",
    "EvidenceTag",
    "FactorDirection",
    "FactorId",
    "FactorSpec",
    "FactorTaxonomy",
    "FactorTier",
    "ImportanceWeightSpec",
    "InterviewBank",
    "InterviewConfig",
    "InterviewItemId",
    "InterviewItemRole",
    "InterviewItemType",
    "Memory",
    "MemoryId",
    "MemoryType",
    "MindtraceError",
    "NormalPrior",
    "OrdinalScale",
    "PairwiseItem",
    "Polarity",
    "PosteriorKind",
    "ProvenanceSource",
    "ReportConfig",
    "ScaleLevel",
    "SchemaBundle",
    "SchemaConsistencyError",
    "SchemaError",
    "SchemaStructureError",
    "SchemaValidationError",
    "SelfReportReliability",
    "TraitModel",
    "UncertainReason",
    "UserId",
    "classify_epistemic_state",
    "load_factor_taxonomy",
    "load_interview_bank",
    "load_schema_bundle",
    "load_trait_model",
    "parse_factor_taxonomy",
    "parse_interview_bank",
    "parse_trait_model",
]
