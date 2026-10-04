"""The Twin aggregate (``docs/architecture/02-domain-model.md`` AG-6; M8).

``Twin`` is thin - a stable identity container. ``TwinVersion`` is the
immutable, tier-B snapshot a ``Simulation``/``Prediction`` actually
references (``mindtrace.domain.simulation``'s own module docstring already
states this invariant: a simulation never resolves "the twin's latest
state", only a specific, already-materialised version).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from mindtrace.domain.decision import DispositionInputs, WeightVector
from mindtrace.domain.enums import TwinVersionReason
from mindtrace.domain.ids import TwinId, TwinVersionId, UserId
from mindtrace.domain.traits import PreferencePosterior

_FrozenModel = ConfigDict(frozen=True, extra="forbid")


class Twin(BaseModel):
    """A user's twin - at most one per user in M8 (AG-6)."""

    model_config = _FrozenModel

    id: TwinId
    user_id: UserId
    name: str
    created_at: datetime


class TwinVersion(BaseModel):
    """One immutable snapshot of a twin's preference posterior (AG-6, tier B).

    ``trait_snapshot`` is the full, lossless :class:`~mindtrace.domain.
    traits.PreferencePosterior` (M8 planning s5) - everything needed to
    reproduce ``weights``/``dispositions`` exactly via
    ``engines.preference.projection.project_effective_weights``.
    ``weights``/``dispositions`` are nonetheless stored separately,
    materialised at creation time: a later change to
    ``project_effective_weights``'s own transformation (a future
    ``PROJECTION_VERSION`` bump) must never silently change what an
    *existing* ``TwinVersion``'s simulations used (M8 planning s5/s12's
    historical-reproducibility requirement).
    """

    model_config = _FrozenModel

    id: TwinVersionId
    user_id: UserId
    twin_id: TwinId
    version: int
    trait_snapshot: PreferencePosterior
    weights: WeightVector
    dispositions: DispositionInputs
    reason: TwinVersionReason
    engine_version: str
    projection_version: str
    factor_schema_version: int
    trait_schema_version: int
    created_at: datetime


__all__ = ["Twin", "TwinVersion"]
