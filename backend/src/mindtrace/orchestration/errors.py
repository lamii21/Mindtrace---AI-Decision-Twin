"""Orchestration-level failures.

Deliberately minimal (M6-B §26): most failure modes already have a home in
the engine that owns them - a failed extraction is an `ExtractionOutcome`
with `status="failed"` (M5), an incompatible posterior raises
`PreferenceValidationError` (M6-A), incompatible weights raise
`MCDAValidationError` (M3) - and `simulate()` lets every one of those
propagate or resolve exactly as its owning engine already defines, rather
than re-wrapping them into a generic `SimulationError` that would destroy
which engine actually detected the problem.

`SimulationError` exists for the one check that has no single owning engine:
whether the `FactorTaxonomy` and `TraitModel` a caller supplies are even
talking about the same factor schema (`taxonomy.version` vs
`trait_model.factor_schema_version`) - `project_effective_weights` never
sees `taxonomy` at all, and `decide()` never sees `trait_model`, so this
cross-check can only happen at the composition point.
"""

from __future__ import annotations

from mindtrace.domain.errors import DomainError


class SimulationError(DomainError):
    """A composition-level invariant was violated - not an engine-level failure."""
