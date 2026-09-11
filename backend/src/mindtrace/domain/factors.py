"""The canonical factor taxonomy: typed model, pure parser, and file loader.

Mirrors ``schema/factors.yaml`` (see ``docs/spec/03-factor-model.md``). The specs
are frozen: once parsed, a :class:`FactorTaxonomy` is read-only data.

- :func:`parse_factor_taxonomy` is pure: ``dict -> FactorTaxonomy``, no I/O.
- :func:`load_factor_taxonomy` is the file seam: read YAML, JSON-Schema check,
  then parse.
"""

from __future__ import annotations

import itertools
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from mindtrace.domain._schema_io import read_json, read_yaml, validate_structure
from mindtrace.domain.enums import (
    FactorDirection,
    FactorTier,
    ScaleLevel,
    SelfReportReliability,
)
from mindtrace.domain.errors import SchemaValidationError
from mindtrace.domain.ids import EvidenceTag, FactorId
from mindtrace.domain.paths import default_schema_dir

_SCHEMA_FILE = "factors.schema.json"
_DATA_FILE = "factors.yaml"

_FrozenModel = ConfigDict(frozen=True, extra="forbid")


class OrdinalScale(BaseModel):
    """The shared ordinal level scale and its default anchor curve."""

    model_config = _FrozenModel

    levels: tuple[ScaleLevel, ...]
    default_anchors: dict[ScaleLevel, float]


class FactorSpec(BaseModel):
    """One decision dimension the MCDA engine scores.

    ``anchors`` is the *effective* anchor curve: the factor's own override if it
    declared one, otherwise the scale default.
    """

    model_config = _FrozenModel

    id: FactorId
    label: str
    description: str
    direction: FactorDirection
    range_min: ScaleLevel
    range_max: ScaleLevel
    better: str  # "higher" | "lower" - cross-checked against direction at parse time
    anchors: dict[ScaleLevel, float]
    has_anchor_override: bool
    examples: tuple[str, ...]
    possible_evidence: tuple[EvidenceTag, ...]
    can_be_inferred: bool
    self_report_reliability: SelfReportReliability
    tier: FactorTier

    def anchor_for(self, level: ScaleLevel) -> float:
        """Return the raw [0, 1] anchor for ``level`` (before any polarity or curve step)."""
        return self.anchors[level]


class FactorTaxonomy(BaseModel):
    """The full taxonomy: core factors, extended factors, and the scale."""

    model_config = _FrozenModel

    version: int
    released: date
    scale: OrdinalScale
    core: tuple[FactorSpec, ...]
    extended: tuple[FactorSpec, ...]

    @property
    def all_factors(self) -> tuple[FactorSpec, ...]:
        """Core factors followed by extended factors, in file order."""
        return self.core + self.extended

    @property
    def core_ids(self) -> tuple[FactorId, ...]:
        """The ids of the core (v1-aggregated) factors, in file order."""
        return tuple(f.id for f in self.core)

    @property
    def all_ids(self) -> frozenset[FactorId]:
        """Every factor id, core and extended."""
        return frozenset(f.id for f in self.all_factors)

    def get(self, factor_id: FactorId | str) -> FactorSpec:
        """Return the factor with ``factor_id``.

        Raises:
            KeyError: if no such factor exists.
        """
        for factor in self.all_factors:
            if factor.id == factor_id:
                return factor
        raise KeyError(factor_id)

    def __contains__(self, factor_id: object) -> bool:
        """True if ``factor_id`` names a known core or extended factor."""
        return isinstance(factor_id, str) and any(f.id == factor_id for f in self.all_factors)


def _effective_anchors(
    raw: dict[str, Any],
    scale: OrdinalScale,
    *,
    factor_id: str,
) -> tuple[dict[ScaleLevel, float], bool]:
    override = raw.get("anchors")
    if override is None:
        return dict(scale.default_anchors), False

    try:
        anchors = {ScaleLevel(k): float(v) for k, v in override.items()}
    except ValueError as exc:
        raise SchemaValidationError(
            f"anchor key is not a scale level ({exc})",
            source=_DATA_FILE,
            location=f"factors/{factor_id}/anchors",
        ) from exc
    return anchors, True


def _check_anchor_curve(anchors: dict[ScaleLevel, float], *, factor_id: str) -> None:
    missing = [lvl.value for lvl in ScaleLevel if lvl not in anchors]
    if missing:
        raise SchemaValidationError(
            f"anchors missing levels {missing}",
            source=_DATA_FILE,
            location=f"factors/{factor_id}/anchors",
        )
    ordered = sorted(anchors.items(), key=lambda kv: kv[0].rank)
    for (low_level, low), (high_level, high) in itertools.pairwise(ordered):
        if not low < high:
            raise SchemaValidationError(
                f"anchors must strictly increase with level; "
                f"{low_level.value}={low} is not < {high_level.value}={high}",
                source=_DATA_FILE,
                location=f"factors/{factor_id}/anchors",
            )
    for level, value in anchors.items():
        if not 0.0 <= value <= 1.0:
            raise SchemaValidationError(
                f"anchor {level.value}={value} is outside [0, 1]",
                source=_DATA_FILE,
                location=f"factors/{factor_id}/anchors",
            )


_DIRECTION_TO_BETTER = {FactorDirection.BENEFIT: "higher", FactorDirection.COST: "lower"}


def _parse_factor(raw: dict[str, Any], scale: OrdinalScale, *, tier: FactorTier) -> FactorSpec:
    factor_id = str(raw["id"])
    direction = FactorDirection(raw["direction"])
    better = str(raw["better"])
    if better != _DIRECTION_TO_BETTER[direction]:
        raise SchemaValidationError(
            f"direction={direction.value} implies better={_DIRECTION_TO_BETTER[direction]!r}, "
            f"but better={better!r}",
            source=_DATA_FILE,
            location=f"factors/{factor_id}",
        )

    range_levels = [ScaleLevel(v) for v in raw["range"]]
    range_min, range_max = range_levels[0], range_levels[-1]
    if range_min.rank > range_max.rank:
        raise SchemaValidationError(
            f"range is descending: {range_min.value} > {range_max.value}",
            source=_DATA_FILE,
            location=f"factors/{factor_id}/range",
        )

    anchors, overridden = _effective_anchors(raw, scale, factor_id=factor_id)
    _check_anchor_curve(anchors, factor_id=factor_id)

    return FactorSpec(
        id=FactorId(factor_id),
        label=str(raw["label"]),
        description=str(raw["description"]).strip(),
        direction=direction,
        range_min=range_min,
        range_max=range_max,
        better=better,
        anchors=anchors,
        has_anchor_override=overridden,
        examples=tuple(raw.get("examples", ())),
        possible_evidence=tuple(EvidenceTag(t) for t in raw.get("possible_evidence", ())),
        can_be_inferred=bool(raw["can_be_inferred"]),
        self_report_reliability=SelfReportReliability(raw["self_report_reliability"]),
        tier=tier,
    )


def parse_factor_taxonomy(data: dict[str, Any]) -> FactorTaxonomy:
    """Build a :class:`FactorTaxonomy` from already-parsed data. Pure; no I/O.

    Raises:
        SchemaValidationError: on a duplicate id, a non-monotone anchor curve, a
            direction/``better`` mismatch, or a bad scale reference.
    """
    scale_raw = data["scale"]
    default_anchors = {ScaleLevel(k): float(v) for k, v in scale_raw["default_anchors"].items()}
    levels = tuple(ScaleLevel(v) for v in scale_raw["levels"])
    if set(default_anchors) != set(ScaleLevel):
        raise SchemaValidationError(
            "scale.default_anchors must define every scale level",
            source=_DATA_FILE,
            location="scale/default_anchors",
        )
    _check_anchor_curve(default_anchors, factor_id="<scale default>")
    scale = OrdinalScale(levels=levels, default_anchors=default_anchors)

    core = tuple(_parse_factor(r, scale, tier=FactorTier.CORE) for r in data["factors"])
    extended = tuple(
        _parse_factor(r, scale, tier=FactorTier.EXTENDED) for r in data.get("extended_factors", ())
    )

    seen: set[str] = set()
    for factor in (*core, *extended):
        if factor.id in seen:
            raise SchemaValidationError(
                f"duplicate factor id {factor.id!r}",
                source=_DATA_FILE,
                location="factors",
            )
        seen.add(factor.id)

    return FactorTaxonomy(
        version=int(data["version"]),
        released=date.fromisoformat(str(data["released"])),
        scale=scale,
        core=core,
        extended=extended,
    )


def load_factor_taxonomy(schema_dir: Path | None = None) -> FactorTaxonomy:
    """Read ``factors.yaml``, structurally validate it, and parse it."""
    directory = schema_dir or default_schema_dir()
    data = read_yaml(directory / _DATA_FILE)
    schema = read_json(directory / _SCHEMA_FILE)
    validate_structure(data, schema, source=_DATA_FILE)
    return parse_factor_taxonomy(data)
