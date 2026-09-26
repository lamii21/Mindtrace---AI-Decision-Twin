"""The decision aggregate (``docs/architecture/02-domain-model.md`` AG-5).

Named ``decision_record`` - not ``decision`` - deliberately: ``mindtrace.domain.decision``
already holds M3's MCDA output types (``DecisionResult``, ``FactorReading``,
``WeightVector``, ``Contribution``, ...), and this is a different concept -
the *situation a user is weighing*, not the *computed answer* to it. Keeping
them in separate modules avoids a name collision without renaming either
milestone's public types (M6-Persistence/Foundation planning review).

This milestone (persistence foundation) only needs the pre-``simulate``
shape: ``extracted_factors``/``extraction_model_run_id``/the prediction and
outcome links are M7+/M8+ fields and are deliberately absent here, the same
way M2's ``Memory`` omits fields its producing engine doesn't exist yet
(``mindtrace.domain.memory`` module docstring) - adding them now with a
placeholder would be exactly the "looks computed but isn't" failure
principle 15 warns about.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from mindtrace.domain.enums import DecisionCategory, DecisionStatus
from mindtrace.domain.ids import DecisionId, UserId

_FrozenModel = ConfigDict(frozen=True, extra="forbid")


class DecisionOption(BaseModel):
    """One named option under consideration (``docs/api/08-api-contracts.md`` s4 ``OptionIn``)."""

    model_config = _FrozenModel

    id: str
    label: str
    body: str


class Decision(BaseModel):
    """One situation a user is weighing, and (once committed) what they chose.

    ``chosen_option`` is a short id referencing one of ``options[].id`` - a
    token, not prose, so it is not itself an encrypted field (M6-Persistence
    planning review s3). The situation fields (``title``/``context``/
    ``options``) become immutable once ``status`` reaches ``simulated`` per
    AG-5 - that guard belongs to the service layer that owns the transaction
    (M7), not to this frozen value type.
    """

    model_config = _FrozenModel

    id: DecisionId
    user_id: UserId
    title: str
    category: DecisionCategory
    context: str
    options: tuple[DecisionOption, ...]
    chosen_option: str | None = None
    reasoning: str | None = None
    decided_at: datetime | None = None
    status: DecisionStatus
    created_at: datetime
