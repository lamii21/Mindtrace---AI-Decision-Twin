"""The canonical parallel-twin transform table: typed model, parser, loader (M10, ADR-007).

Mirrors ``schema/twins.yaml``. A :class:`TwinDefinition` names, for one
parallel twin, which :class:`~mindtrace.domain.ids.FactorId` values get
up/down shifted relative to the user's own base effective weight vector -
never a prompt, never a persona, never an LLM-generated weight (ADR-007). The
shared ``lambda`` constant and the actual renormalisation math live in
``engines.simulation.parallel`` - this module only loads and validates the
declarative transform table itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from mindtrace.domain._schema_io import read_json, read_yaml, validate_structure
from mindtrace.domain.errors import SchemaConsistencyError, SchemaValidationError
from mindtrace.domain.factors import FactorTaxonomy
from mindtrace.domain.ids import FactorId
from mindtrace.domain.paths import default_schema_dir

_SCHEMA_FILE = "twins.schema.json"
_DATA_FILE = "twins.yaml"

_FrozenModel = ConfigDict(frozen=True, extra="forbid")

#: The reserved id for the user's own, untransformed effective weight vector -
#: never listed in ``twins.yaml`` (it is not a transform), but every ensemble/
#: synthesis function treats it as "one of the twins" per ADR-007.
BASE_TWIN_ID = "base"


class TwinDefinition(BaseModel):
    """One named, fixed shift (ADR-007) - up-weighted and down-weighted factors, nothing else."""

    model_config = _FrozenModel

    id: str
    label: str
    up: tuple[FactorId, ...]
    down: tuple[FactorId, ...]

    @model_validator(mode="after")
    def _up_down_disjoint(self) -> TwinDefinition:
        overlap = frozenset(self.up) & frozenset(self.down)
        if overlap:
            msg = f"twin {self.id!r}: factors in both up and down: {sorted(overlap)}"
            raise SchemaValidationError(msg, source=_DATA_FILE, location=f"twins/{self.id}")
        return self


class TwinTable(BaseModel):
    """The full parallel-twin transform table bound to a factor schema version."""

    model_config = _FrozenModel

    version: int
    factor_schema_version: int
    lambda_: float
    twins: tuple[TwinDefinition, ...]

    @field_validator("twins")
    @classmethod
    def _ids_unique_and_not_base(
        cls, value: tuple[TwinDefinition, ...]
    ) -> tuple[TwinDefinition, ...]:
        if not value:
            # Matches ``twins.schema.json``'s own ``"minItems": 1`` on this same array
            # (post-M10 audit F3) - that JSON Schema check only runs at the file-loading
            # boundary (``load_twin_table``); constructing a ``TwinTable`` directly in
            # Python (as ``parse_twin_table``, and any future caller, can) bypassed it
            # entirely, letting an empty table reach ``run_twin_ensemble``/
            # ``ensemble_observation_from`` and fail there instead, as an unrelated
            # ``pydantic.ValidationError`` about ``EnsembleObservation`` needing >= 2
            # scores - a confusing failure far from its real cause. This enforces the
            # already-authoritative "at least one twin" contract at the domain type
            # itself, not merely at the file-loading boundary.
            msg = "a twin table must declare at least one twin"
            raise SchemaValidationError(msg, source=_DATA_FILE, location="twins")
        ids = [twin.id for twin in value]
        if len(ids) != len(set(ids)):
            msg = f"duplicate twin ids: {ids}"
            raise SchemaValidationError(msg, source=_DATA_FILE, location="twins")
        if BASE_TWIN_ID in ids:
            msg = f"{BASE_TWIN_ID!r} is reserved for the untransformed base twin"
            raise SchemaValidationError(msg, source=_DATA_FILE, location="twins")
        return value


def parse_twin_table(data: dict[str, Any], *, taxonomy: FactorTaxonomy) -> TwinTable:
    """Build a :class:`TwinTable`, validated against ``taxonomy``. Pure.

    Raises:
        SchemaConsistencyError: ``factor_schema_version`` does not match
            ``taxonomy.version``, or a twin names an unknown factor.
        SchemaValidationError: duplicate twin ids, a twin reusing the
            reserved ``"base"`` id, or a factor listed in both ``up`` and
            ``down`` for the same twin.
    """
    factor_schema_version = int(data["factor_schema_version"])
    if factor_schema_version != taxonomy.version:
        raise SchemaConsistencyError(
            f"factor_schema_version={factor_schema_version} does not match "
            f"factors.yaml version={taxonomy.version}",
            source=_DATA_FILE,
            location="factor_schema_version",
        )

    twins = tuple(
        TwinDefinition(
            id=str(raw["id"]),
            label=str(raw["label"]),
            up=tuple(FactorId(str(f)) for f in raw["up"]),
            down=tuple(FactorId(str(f)) for f in raw["down"]),
        )
        for raw in data["twins"]
    )
    table = TwinTable(
        version=int(data["version"]),
        factor_schema_version=factor_schema_version,
        lambda_=float(data["lambda"]),
        twins=twins,
    )
    _validate_factor_references(table, taxonomy)
    return table


def _validate_factor_references(table: TwinTable, taxonomy: FactorTaxonomy) -> None:
    known = taxonomy.all_ids
    for twin in table.twins:
        for factor_id in (*twin.up, *twin.down):
            if factor_id not in known:
                raise SchemaConsistencyError(
                    f"twin {twin.id!r} references unknown factor {factor_id!r}",
                    source=_DATA_FILE,
                    location=f"twins/{twin.id}",
                )


def load_twin_table(schema_dir: Path | None = None, *, taxonomy: FactorTaxonomy) -> TwinTable:
    """Read ``twins.yaml``, structurally validate it, and parse it against ``taxonomy``."""
    directory = schema_dir or default_schema_dir()
    data = read_yaml(directory / _DATA_FILE)
    schema = read_json(directory / _SCHEMA_FILE)
    validate_structure(data, schema, source=_DATA_FILE)
    return parse_twin_table(data, taxonomy=taxonomy)


__all__ = [
    "BASE_TWIN_ID",
    "TwinDefinition",
    "TwinTable",
    "load_twin_table",
    "parse_twin_table",
]
