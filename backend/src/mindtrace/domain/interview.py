"""The canonical Twin Interview item bank: typed model, pure parser, file loader.

Mirrors ``schema/interview.yaml`` (see ``docs/spec/07-cold-start-interview.md``).
M1 loads and validates the declarative bank only. The Bradley-Terry design
vectors, adaptive selection, and posterior updates are milestone M8 -- this
module deliberately does not compute them.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from mindtrace.domain._schema_io import read_json, read_yaml, validate_structure
from mindtrace.domain.enums import (
    SCALE_LEVEL_CODES,
    ChoiceOption,
    InterviewItemRole,
    InterviewItemType,
    ScaleLevel,
)
from mindtrace.domain.errors import SchemaConsistencyError, SchemaValidationError
from mindtrace.domain.factors import FactorTaxonomy
from mindtrace.domain.ids import DispositionId, FactorId, InterviewItemId
from mindtrace.domain.paths import default_schema_dir
from mindtrace.domain.traits import TraitModel

_SCHEMA_FILE = "interview.schema.json"
_DATA_FILE = "interview.yaml"

_FrozenModel = ConfigDict(frozen=True, extra="forbid")

# yaml disposition key -> the item type it belongs to
_KEYED_FIELDS: dict[str, InterviewItemType] = {
    "risky_option": InterviewItemType.GAMBLE,
    "patient_option": InterviewItemType.INTERTEMPORAL,
    "ambiguity_seeking_option": InterviewItemType.AMBIGUITY,
    "high_effort_option": InterviewItemType.EFFORT,
}


class InterviewConfig(BaseModel):
    """Interview flow configuration (item counts, stopping rule, scoring constants)."""

    model_config = _FrozenModel

    likert_warmup_factors: tuple[FactorId, ...]
    fixed_prefix_items: int
    adaptive_suffix_max: int
    target_total_min: int
    target_total_max: int
    logistic_scale_s: float
    pseudocount_kappa: float
    consistency_check_item_ids: tuple[InterviewItemId, ...]


class PairwiseItem(BaseModel):
    """A forced choice between two synthetic option profiles (updates weight logits)."""

    model_config = _FrozenModel

    id: InterviewItemId
    type: InterviewItemType = InterviewItemType.PAIRWISE
    role: InterviewItemRole
    prompt_a: str
    prompt_b: str
    profile_a: dict[FactorId, ScaleLevel]
    profile_b: dict[FactorId, ScaleLevel]
    covers: tuple[FactorId, ...]

    @property
    def varied_factors(self) -> frozenset[FactorId]:
        """Factors that appear in either option profile."""
        return frozenset(self.profile_a) | frozenset(self.profile_b)


class DispositionItem(BaseModel):
    """A forced choice targeting one disposition (updates a Beta posterior).

    ``keyed_option`` is the side whose selection the yaml flags (``risky_option``,
    ``patient_option``, ...). Turning that into ``y in {0, 1}`` -- including the
    inversion for ``time_discount`` / ``ambiguity_aversion`` -- is M8's job.
    """

    model_config = _FrozenModel

    id: InterviewItemId
    type: InterviewItemType
    target: DispositionId
    prompt_a: str
    prompt_b: str
    keyed_field: str
    keyed_option: ChoiceOption


class InterviewBank(BaseModel):
    """The full item bank bound to a factor schema version."""

    model_config = _FrozenModel

    version: int
    released: date
    factor_schema_version: int
    config: InterviewConfig
    pairwise: tuple[PairwiseItem, ...]
    disposition: tuple[DispositionItem, ...]

    @property
    def item_ids(self) -> tuple[InterviewItemId, ...]:
        """Ids of every item, pairwise then disposition, in file order."""
        pairwise_ids = tuple(item.id for item in self.pairwise)
        disposition_ids = tuple(item.id for item in self.disposition)
        return pairwise_ids + disposition_ids

    @property
    def total_items(self) -> int:
        """Total number of items in the bank."""
        return len(self.pairwise) + len(self.disposition)


def _levels_from_codes(
    profile: dict[str, Any], *, item_id: str, side: str
) -> dict[FactorId, ScaleLevel]:
    out: dict[FactorId, ScaleLevel] = {}
    for factor_raw, code in profile.items():
        level = SCALE_LEVEL_CODES.get(str(code))
        if level is None:
            raise SchemaValidationError(
                f"unknown level code {code!r} (expected one of {sorted(SCALE_LEVEL_CODES)})",
                source=_DATA_FILE,
                location=f"pairwise/{item_id}/{side}/{factor_raw}",
            )
        out[FactorId(str(factor_raw))] = level
    return out


def _parse_pairwise(raw: dict[str, Any]) -> PairwiseItem:
    item_id = str(raw["id"])
    role = (
        InterviewItemRole.CONSISTENCY_CHECK
        if raw.get("role") == "consistency_check"
        else InterviewItemRole.STANDARD
    )
    profile_a = _levels_from_codes(raw["A"], item_id=item_id, side="A")
    profile_b = _levels_from_codes(raw["B"], item_id=item_id, side="B")
    covers = tuple(FactorId(str(c)) for c in raw["covers"])

    item = PairwiseItem(
        id=InterviewItemId(item_id),
        role=role,
        prompt_a=str(raw["prompt_A"]),
        prompt_b=str(raw["prompt_B"]),
        profile_a=profile_a,
        profile_b=profile_b,
        covers=covers,
    )
    if frozenset(covers) != item.varied_factors:
        raise SchemaValidationError(
            f"'covers' {sorted(covers)} does not match the factors varied in the profiles "
            f"{sorted(item.varied_factors)}",
            source=_DATA_FILE,
            location=f"pairwise/{item_id}/covers",
        )
    return item


def _parse_disposition_item(raw: dict[str, Any]) -> DispositionItem:
    item_id = str(raw["id"])
    item_type = InterviewItemType(raw["type"])
    present = [k for k in _KEYED_FIELDS if k in raw]
    if len(present) != 1:
        raise SchemaValidationError(
            f"disposition item must declare exactly one of {sorted(_KEYED_FIELDS)}, "
            f"found {present}",
            source=_DATA_FILE,
            location=f"disposition/{item_id}",
        )
    keyed_field = present[0]
    if _KEYED_FIELDS[keyed_field] is not item_type:
        raise SchemaValidationError(
            f"item type {item_type.value!r} does not match keyed field {keyed_field!r} "
            f"(expected {_KEYED_FIELDS[keyed_field].value!r})",
            source=_DATA_FILE,
            location=f"disposition/{item_id}",
        )
    return DispositionItem(
        id=InterviewItemId(item_id),
        type=item_type,
        target=DispositionId(str(raw["target"])),
        prompt_a=str(raw["prompt_A"]),
        prompt_b=str(raw["prompt_B"]),
        keyed_field=keyed_field,
        keyed_option=ChoiceOption(raw[keyed_field]),
    )


def _parse_config(raw: dict[str, Any]) -> InterviewConfig:
    target = raw["target_total"]
    lo, hi = int(target[0]), int(target[1])
    if lo > hi:
        raise SchemaValidationError(
            f"target_total is descending: [{lo}, {hi}]",
            source=_DATA_FILE,
            location="config/target_total",
        )
    return InterviewConfig(
        likert_warmup_factors=tuple(FactorId(str(f)) for f in raw["likert_warmup_factors"]),
        fixed_prefix_items=int(raw["fixed_prefix_items"]),
        adaptive_suffix_max=int(raw["adaptive_suffix_max"]),
        target_total_min=lo,
        target_total_max=hi,
        logistic_scale_s=float(raw["logistic_scale_s"]),
        pseudocount_kappa=float(raw["pseudocount_kappa"]),
        consistency_check_item_ids=tuple(
            InterviewItemId(str(i)) for i in raw["consistency_check_item_ids"]
        ),
    )


def parse_interview_bank(
    data: dict[str, Any],
    *,
    taxonomy: FactorTaxonomy,
    trait_model: TraitModel,
) -> InterviewBank:
    """Build an :class:`InterviewBank`, validated against the taxonomy and trait model. Pure.

    Raises:
        SchemaConsistencyError: on a version mismatch or a reference to an
            unknown factor / disposition.
        SchemaValidationError: on duplicate item ids, semantically duplicated
            items, a ``covers`` mismatch, or an inconsistent consistency-check
            reference.
    """
    factor_schema_version = int(data["factor_schema_version"])
    if factor_schema_version != taxonomy.version:
        raise SchemaConsistencyError(
            f"factor_schema_version={factor_schema_version} does not match "
            f"factors.yaml version={taxonomy.version}",
            source=_DATA_FILE,
            location="factor_schema_version",
        )

    config = _parse_config(data["config"])
    pairwise = tuple(_parse_pairwise(r) for r in data["pairwise"])
    disposition = tuple(_parse_disposition_item(r) for r in data["disposition"])

    bank = InterviewBank(
        version=int(data["version"]),
        released=date.fromisoformat(str(data["released"])),
        factor_schema_version=factor_schema_version,
        config=config,
        pairwise=pairwise,
        disposition=disposition,
    )

    _validate_item_ids(bank)
    _validate_no_semantic_duplicates(pairwise)
    _validate_factor_references(bank, taxonomy)
    _validate_disposition_targets(disposition, trait_model)
    _validate_consistency_checks(bank)
    _validate_counts(bank)
    return bank


def _validate_item_ids(bank: InterviewBank) -> None:
    seen: set[str] = set()
    for item_id in bank.item_ids:
        if item_id in seen:
            raise SchemaValidationError(
                f"duplicate interview item id {item_id!r}",
                source=_DATA_FILE,
                location="pairwise|disposition",
            )
        seen.add(item_id)


def _validate_no_semantic_duplicates(pairwise: tuple[PairwiseItem, ...]) -> None:
    seen: dict[tuple[str, str, tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]], str] = {}
    for item in pairwise:
        key = (
            item.prompt_a,
            item.prompt_b,
            tuple(sorted((k, v.value) for k, v in item.profile_a.items())),
            tuple(sorted((k, v.value) for k, v in item.profile_b.items())),
        )
        if key in seen:
            raise SchemaValidationError(
                f"pairwise items {seen[key]!r} and {item.id!r} are identical",
                source=_DATA_FILE,
                location="pairwise",
            )
        seen[key] = item.id


def _validate_factor_references(bank: InterviewBank, taxonomy: FactorTaxonomy) -> None:
    known = taxonomy.all_ids

    def _check(factor_id: FactorId, where: str) -> None:
        if factor_id not in known:
            raise SchemaConsistencyError(
                f"references unknown factor {factor_id!r}",
                source=_DATA_FILE,
                location=where,
            )

    for factor_id in bank.config.likert_warmup_factors:
        _check(factor_id, "config/likert_warmup_factors")
    for item in bank.pairwise:
        for factor_id in item.varied_factors:
            _check(factor_id, f"pairwise/{item.id}")
        for factor_id in item.covers:
            _check(factor_id, f"pairwise/{item.id}/covers")


def _validate_disposition_targets(
    disposition: tuple[DispositionItem, ...],
    trait_model: TraitModel,
) -> None:
    known = frozenset(trait_model.disposition_ids)
    for item in disposition:
        if item.target not in known:
            raise SchemaConsistencyError(
                f"disposition item {item.id!r} targets unknown disposition {item.target!r} "
                f"(known: {sorted(known)})",
                source=_DATA_FILE,
                location=f"disposition/{item.id}/target",
            )


def _validate_consistency_checks(bank: InterviewBank) -> None:
    pairwise_by_id = {i.id: i for i in bank.pairwise}
    for item_id in bank.config.consistency_check_item_ids:
        item = pairwise_by_id.get(item_id)
        if item is None:
            raise SchemaValidationError(
                f"consistency_check_item_ids references unknown pairwise item {item_id!r}",
                source=_DATA_FILE,
                location="config/consistency_check_item_ids",
            )
        if item.role is not InterviewItemRole.CONSISTENCY_CHECK:
            raise SchemaValidationError(
                f"item {item_id!r} is listed as a consistency check but its role is "
                f"{item.role.value!r}",
                source=_DATA_FILE,
                location=f"pairwise/{item_id}/role",
            )


def _validate_counts(bank: InterviewBank) -> None:
    total = bank.total_items
    cfg = bank.config
    if cfg.fixed_prefix_items > total:
        raise SchemaValidationError(
            f"fixed_prefix_items={cfg.fixed_prefix_items} exceeds the {total} items in the bank",
            source=_DATA_FILE,
            location="config/fixed_prefix_items",
        )
    if cfg.target_total_max > total:
        raise SchemaValidationError(
            f"target_total max={cfg.target_total_max} exceeds the {total} items in the bank",
            source=_DATA_FILE,
            location="config/target_total",
        )


def load_interview_bank(
    schema_dir: Path | None = None,
    *,
    taxonomy: FactorTaxonomy,
    trait_model: TraitModel,
) -> InterviewBank:
    """Read ``interview.yaml``, structurally validate it, and parse it against the other schemas."""
    directory = schema_dir or default_schema_dir()
    data = read_yaml(directory / _DATA_FILE)
    schema = read_json(directory / _SCHEMA_FILE)
    validate_structure(data, schema, source=_DATA_FILE)
    return parse_interview_bank(data, taxonomy=taxonomy, trait_model=trait_model)
