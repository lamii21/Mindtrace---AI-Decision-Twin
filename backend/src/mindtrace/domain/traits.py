"""The canonical trait model: typed model, pure parser, and file loader.

Mirrors ``schema/traits.yaml`` (see ``docs/spec/04-trait-model.md``). Two kinds of
trait: one importance weight per factor (Normal logit posterior) and a small set
of dispositions (Beta posteriors). M1 loads and validates the declarations only.
Posterior updating (ADR-005) is ``mindtrace.engines.preference`` (M4); the
posterior/observation/report value types it consumes and produces live here,
alongside the priors they start from - the same relationship
``domain/decision.py``/``engines/mcda`` has.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mindtrace.domain._schema_io import read_json, read_yaml, validate_structure
from mindtrace.domain.enums import FactorTier, PosteriorKind, SelfReportReliability
from mindtrace.domain.errors import SchemaConsistencyError, SchemaValidationError
from mindtrace.domain.factors import FactorTaxonomy
from mindtrace.domain.ids import DispositionId, EvidenceTag, FactorId
from mindtrace.domain.paths import default_schema_dir

_SCHEMA_FILE = "traits.schema.json"
_DATA_FILE = "traits.yaml"

_FrozenModel = ConfigDict(frozen=True, extra="forbid")


class NormalPrior(BaseModel):
    """A Normal prior on a trait logit: ``theta ~ N(mu, sigma**2)``."""

    model_config = _FrozenModel

    mu: float
    sigma: float

    @field_validator("sigma")
    @classmethod
    def _sigma_positive(cls, value: float) -> float:
        if value <= 0:
            msg = f"sigma must be > 0, got {value}"
            raise ValueError(msg)
        return value


class BetaPrior(BaseModel):
    """A Beta prior on a bounded [0, 1] disposition: ``p ~ Beta(alpha, beta)``."""

    model_config = _FrozenModel

    alpha: float
    beta: float

    @field_validator("alpha", "beta")
    @classmethod
    def _positive(cls, value: float) -> float:
        if value <= 0:
            msg = f"Beta parameters must be > 0, got {value}"
            raise ValueError(msg)
        return value


class ImportanceWeightSpec(BaseModel):
    """The prior for one factor's importance weight."""

    model_config = _FrozenModel

    factor: FactorId
    prior: NormalPrior
    self_report_reliability: SelfReportReliability
    tier: FactorTier


class DispositionSpec(BaseModel):
    """A latent disposition that modulates the MCDA (curve shapes, twin shifts)."""

    model_config = _FrozenModel

    id: DispositionId
    description: str
    prior: BetaPrior
    kind: str
    inferable_from: tuple[EvidenceTag, ...]
    mechanical_effect: str


class ReportConfig(BaseModel):
    """Thresholds governing how traits are surfaced to the API/UI."""

    model_config = _FrozenModel

    low_confidence_threshold: float
    min_evidence_for_inferred: int


class TraitModel(BaseModel):
    """The full trait model bound to a factor schema version."""

    model_config = _FrozenModel

    version: int
    released: date
    factor_schema_version: int
    prior_defaults: NormalPrior
    read_transform: str
    weight_credible_interval: float
    disposition_credible_interval: float
    weights: tuple[ImportanceWeightSpec, ...]
    dispositions: tuple[DispositionSpec, ...]
    report: ReportConfig

    @property
    def weight_factor_ids(self) -> frozenset[FactorId]:
        """Ids of every factor that has an importance weight."""
        return frozenset(w.factor for w in self.weights)

    @property
    def disposition_ids(self) -> tuple[DispositionId, ...]:
        """Ids of every disposition, in file order."""
        return tuple(d.id for d in self.dispositions)

    def weight_for(self, factor_id: FactorId | str) -> ImportanceWeightSpec:
        """Return the importance-weight prior for ``factor_id``.

        Raises:
            KeyError: if no weight is declared for that factor.
        """
        for weight in self.weights:
            if weight.factor == factor_id:
                return weight
        raise KeyError(factor_id)

    def disposition_for(self, disposition_id: DispositionId | str) -> DispositionSpec:
        """Return the disposition with ``disposition_id``.

        Raises:
            KeyError: if no such disposition exists.
        """
        for disposition in self.dispositions:
            if disposition.id == disposition_id:
                return disposition
        raise KeyError(disposition_id)


def _parse_weight(raw: dict[str, Any]) -> ImportanceWeightSpec:
    tier = FactorTier(raw["tier"]) if raw.get("tier") else FactorTier.CORE
    return ImportanceWeightSpec(
        factor=FactorId(str(raw["factor"])),
        prior=NormalPrior(mu=float(raw["prior"]["mu"]), sigma=float(raw["prior"]["sigma"])),
        self_report_reliability=SelfReportReliability(raw["self_report_reliability"]),
        tier=tier,
    )


def _parse_disposition(raw: dict[str, Any]) -> DispositionSpec:
    if raw["kind"] != "latent":
        raise SchemaValidationError(
            f"disposition kind must be 'latent', got {raw['kind']!r}",
            source=_DATA_FILE,
            location=f"dispositions/{raw['id']}/kind",
        )
    return DispositionSpec(
        id=DispositionId(str(raw["id"])),
        description=str(raw["description"]).strip(),
        prior=BetaPrior(alpha=float(raw["prior"]["alpha"]), beta=float(raw["prior"]["beta"])),
        kind="latent",
        inferable_from=tuple(EvidenceTag(t) for t in raw["inferable_from"]),
        mechanical_effect=str(raw["mechanical_effect"]).strip(),
    )


def parse_trait_model(data: dict[str, Any], taxonomy: FactorTaxonomy) -> TraitModel:
    """Build a :class:`TraitModel`, validated against ``taxonomy``. Pure; no I/O.

    Raises:
        SchemaConsistencyError: if ``factor_schema_version`` != the taxonomy
            version, or a weight references an unknown factor, or a core factor
            has no weight.
        SchemaValidationError: on duplicate ids, a tier mismatch, or a bad
            posterior kind.
    """
    weights_block = data["importance_weights"]
    if PosteriorKind(weights_block["posterior"]) is not PosteriorKind.NORMAL:
        raise SchemaValidationError(
            "importance_weights.posterior must be 'normal'",
            source=_DATA_FILE,
            location="importance_weights/posterior",
        )
    dispositions_block = data["dispositions"]
    if PosteriorKind(dispositions_block["posterior"]) is not PosteriorKind.BETA:
        raise SchemaValidationError(
            "dispositions.posterior must be 'beta'",
            source=_DATA_FILE,
            location="dispositions/posterior",
        )

    factor_schema_version = int(data["factor_schema_version"])
    if factor_schema_version != taxonomy.version:
        raise SchemaConsistencyError(
            f"factor_schema_version={factor_schema_version} does not match "
            f"factors.yaml version={taxonomy.version}",
            source=_DATA_FILE,
            location="factor_schema_version",
        )

    weights = tuple(_parse_weight(r) for r in weights_block["traits"])
    dispositions = tuple(_parse_disposition(r) for r in dispositions_block["traits"])

    _validate_weight_coverage(weights, taxonomy)
    _validate_unique_ids(weights, dispositions)

    return TraitModel(
        version=int(data["version"]),
        released=date.fromisoformat(str(data["released"])),
        factor_schema_version=factor_schema_version,
        prior_defaults=NormalPrior(
            mu=float(weights_block["prior_defaults"]["mu"]),
            sigma=float(weights_block["prior_defaults"]["sigma"]),
        ),
        read_transform=str(weights_block["read_transform"]),
        weight_credible_interval=float(weights_block["credible_interval"]),
        disposition_credible_interval=float(dispositions_block["credible_interval"]),
        weights=weights,
        dispositions=dispositions,
        report=ReportConfig(
            low_confidence_threshold=float(data["report"]["low_confidence_threshold"]),
            min_evidence_for_inferred=int(data["report"]["min_evidence_for_inferred"]),
        ),
    )


def _validate_weight_coverage(
    weights: tuple[ImportanceWeightSpec, ...],
    taxonomy: FactorTaxonomy,
) -> None:
    known = taxonomy.all_ids
    core_ids = frozenset(taxonomy.core_ids)
    extended_ids = frozenset(f.id for f in taxonomy.extended)

    for weight in weights:
        if weight.factor not in known:
            raise SchemaConsistencyError(
                f"importance weight references unknown factor {weight.factor!r}",
                source=_DATA_FILE,
                location=f"importance_weights/traits/{weight.factor}",
            )
        expected_tier = FactorTier.EXTENDED if weight.factor in extended_ids else FactorTier.CORE
        if weight.tier is not expected_tier:
            raise SchemaValidationError(
                f"weight for {weight.factor!r} is tagged tier={weight.tier.value} "
                f"but the factor is {expected_tier.value}",
                source=_DATA_FILE,
                location=f"importance_weights/traits/{weight.factor}",
            )

    weighted = {w.factor for w in weights}
    missing_core = sorted(core_ids - weighted)
    if missing_core:
        raise SchemaConsistencyError(
            f"core factors have no importance weight: {missing_core}",
            source=_DATA_FILE,
            location="importance_weights/traits",
        )


def _validate_unique_ids(
    weights: tuple[ImportanceWeightSpec, ...],
    dispositions: tuple[DispositionSpec, ...],
) -> None:
    seen_factors: set[str] = set()
    for weight in weights:
        if weight.factor in seen_factors:
            raise SchemaValidationError(
                f"duplicate importance weight for factor {weight.factor!r}",
                source=_DATA_FILE,
                location="importance_weights/traits",
            )
        seen_factors.add(weight.factor)

    seen_dispositions: set[str] = set()
    for disposition in dispositions:
        if disposition.id in seen_dispositions:
            raise SchemaValidationError(
                f"duplicate disposition id {disposition.id!r}",
                source=_DATA_FILE,
                location="dispositions/traits",
            )
        seen_dispositions.add(disposition.id)


def load_trait_model(
    schema_dir: Path | None = None,
    *,
    taxonomy: FactorTaxonomy,
) -> TraitModel:
    """Read ``traits.yaml``, structurally validate it, and parse it against ``taxonomy``."""
    directory = schema_dir or default_schema_dir()
    data = read_yaml(directory / _DATA_FILE)
    schema = read_json(directory / _SCHEMA_FILE)
    validate_structure(data, schema, source=_DATA_FILE)
    return parse_trait_model(data, taxonomy)


# --- Preference engine (M4, ADR-005): posterior state, observations, reports ---------------


class WeightPosterior(BaseModel):
    """`theta_i ~ Normal(mu_i, sigma_i**2)` - a weight's current posterior on the logit scale.

    Identical shape to :class:`NormalPrior`; kept as its own type because a
    posterior and a prior are different things even when they share a
    parametrisation (before any evidence, ``mindtrace.engines.preference.prior``
    builds one from the other, one-to-one).
    """

    model_config = _FrozenModel

    factor: FactorId
    mu: float
    sigma: float

    @field_validator("sigma")
    @classmethod
    def _sigma_positive(cls, value: float) -> float:
        if value <= 0:
            msg = f"sigma must be > 0, got {value}"
            raise ValueError(msg)
        return value


class DispositionPosterior(BaseModel):
    """`p ~ Beta(alpha, beta)` - a disposition's current posterior."""

    model_config = _FrozenModel

    id: DispositionId
    alpha: float
    beta: float

    @field_validator("alpha", "beta")
    @classmethod
    def _positive(cls, value: float) -> float:
        if value <= 0:
            msg = f"Beta parameters must be > 0, got {value}"
            raise ValueError(msg)
        return value


class PairwiseObservation(BaseModel):
    """One forced-choice comparison, already reduced to Bradley-Terry input form.

    Spec/04 §3, spec/07 §4.1: a design vector, an outcome, and an observation
    weight. Turning a real interview answer or observed decision into this shape - which
    factor levels the compared options had, which direction the choice implies,
    how to fold "indifferent" into a fractional ``outcome``/``weight`` - is the
    caller's job (``mindtrace.domain.interview``'s own module docstring reserves
    that conversion for milestone M8's elicitation session). This type is the
    engine's actual mathematical contract: nothing about *where* the comparison
    came from.
    """

    model_config = _FrozenModel

    design: dict[FactorId, float]
    outcome: float = Field(ge=0.0, le=1.0)
    weight: float = Field(gt=0.0, le=1.0)

    @field_validator("design")
    @classmethod
    def _design_non_empty(cls, value: dict[FactorId, float]) -> dict[FactorId, float]:
        if not value:
            msg = "design must vary at least one factor"
            raise ValueError(msg)
        return value


class DispositionObservation(BaseModel):
    """One forced-choice comparison targeting a single disposition (spec/07 §4.2).

    ``outcome`` is already the effective ``y`` the pseudo-count update consumes -
    including the sign inversion spec/07 §4.2's table requires for
    ``time_discount``/``ambiguity_aversion`` (the caller's job, per the same
    M8 boundary noted on :class:`PairwiseObservation`).
    """

    model_config = _FrozenModel

    target: DispositionId
    outcome: float = Field(ge=0.0, le=1.0)


class PreferencePosterior(BaseModel):
    """The preference engine's complete, self-contained state.

    Every trait's posterior, plus how many observations have touched each one.
    This is what a later milestone's persistence layer snapshots into
    ``TwinVersion.trait_snapshot`` (``docs/architecture/02-domain-model.md`` AG-6) -
    M4 itself holds no persistence, no `Twin`, no `TwinVersion`.
    """

    model_config = _FrozenModel

    engine_version: str
    trait_schema_version: int
    weights: dict[FactorId, WeightPosterior]
    dispositions: dict[DispositionId, DispositionPosterior]
    weight_evidence_count: dict[FactorId, int]
    disposition_evidence_count: dict[DispositionId, int]

    @model_validator(mode="after")
    def _validate(self) -> PreferencePosterior:
        if set(self.weights) != set(self.weight_evidence_count):
            msg = "weight_evidence_count must have exactly the same keys as weights"
            raise ValueError(msg)
        if set(self.dispositions) != set(self.disposition_evidence_count):
            msg = "disposition_evidence_count must have exactly the same keys as dispositions"
            raise ValueError(msg)
        for factor_id, count in self.weight_evidence_count.items():
            if count < 0:
                msg = f"evidence count for {factor_id!r} is negative: {count}"
                raise ValueError(msg)
        for disposition_id, count in self.disposition_evidence_count.items():
            if count < 0:
                msg = f"evidence count for {disposition_id!r} is negative: {count}"
                raise ValueError(msg)
        return self


class CredibleInterval(BaseModel):
    """A central marginal interval on a trait's reporting scale (spec/04 §5)."""

    model_config = _FrozenModel

    low: float
    high: float

    @model_validator(mode="after")
    def _validate(self) -> CredibleInterval:
        if self.low > self.high:
            msg = f"low ({self.low}) must not exceed high ({self.high})"
            raise ValueError(msg)
        return self


class TraitReport(BaseModel):
    """One trait's read-side summary, the exact shape spec/04 §5 defines for the API/UI."""

    model_config = _FrozenModel

    id: str
    value: float
    confidence: float = Field(ge=0.0, le=1.0)
    credible_interval: CredibleInterval
    evidence_count: int = Field(ge=0)
    source: str  # "declared" | "inferred"

    @field_validator("source")
    @classmethod
    def _source_valid(cls, value: str) -> str:
        if value not in {"declared", "inferred"}:
            msg = f"source must be 'declared' or 'inferred', got {value!r}"
            raise ValueError(msg)
        return value
