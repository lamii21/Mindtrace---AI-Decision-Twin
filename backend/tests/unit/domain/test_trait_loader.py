"""Tests for the trait model loader/parser (``mindtrace.domain.traits``)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from mindtrace.domain.errors import (
    SchemaConsistencyError,
    SchemaStructureError,
    SchemaValidationError,
)
from mindtrace.domain.factors import FactorTaxonomy, load_factor_taxonomy
from mindtrace.domain.schema_bundle import SchemaBundle
from mindtrace.domain.traits import TraitModel, load_trait_model, parse_trait_model
from tests.support.schema_factories import (
    deep_copy,
    minimal_traits_dict,
    write_bundle,
)

# ---------------------------------------------------------------------------
# Happy path: the real, checked-in trait model
# ---------------------------------------------------------------------------


class TestRealTraitModel:
    def test_loads(self, real_schema_dir: Path, real_bundle: SchemaBundle) -> None:
        traits = load_trait_model(real_schema_dir, taxonomy=real_bundle.factors)
        assert isinstance(traits, TraitModel)

    def test_every_core_and_extended_factor_has_exactly_one_weight(
        self, real_bundle: SchemaBundle
    ) -> None:
        weighted = [w.factor for w in real_bundle.traits.weights]
        assert sorted(weighted) == sorted(set(weighted)), "a factor has more than one weight"
        assert real_bundle.traits.weight_factor_ids == real_bundle.factors.all_ids

    def test_has_four_dispositions(self, real_bundle: SchemaBundle) -> None:
        assert real_bundle.traits.disposition_ids == (
            "risk_tolerance",
            "time_discount",
            "ambiguity_aversion",
            "effort_tolerance",
        )

    def test_extended_factor_weights_are_tagged_extended_tier(
        self, real_bundle: SchemaBundle
    ) -> None:
        extended_ids = {f.id for f in real_bundle.factors.extended}
        for weight in real_bundle.traits.weights:
            if weight.factor in extended_ids:
                assert weight.tier.value == "extended", weight.factor

    def test_factor_schema_version_matches(self, real_bundle: SchemaBundle) -> None:
        assert real_bundle.traits.factor_schema_version == real_bundle.factors.version

    def test_weight_for_and_disposition_for(self, real_bundle: SchemaBundle) -> None:
        weight = real_bundle.traits.weight_for("skill_growth")
        assert weight.self_report_reliability.value == "high"
        disposition = real_bundle.traits.disposition_for("risk_tolerance")
        assert disposition.prior.alpha == 2.0
        with pytest.raises(KeyError):
            real_bundle.traits.weight_for("not_a_factor")
        with pytest.raises(KeyError):
            real_bundle.traits.disposition_for("not_a_disposition")


# ---------------------------------------------------------------------------
# Minimal fixture
# ---------------------------------------------------------------------------


def test_minimal_fixture_parses(minimal_trait_model: TraitModel) -> None:
    assert minimal_trait_model.weight_factor_ids == {"alpha", "beta", "gamma"}
    assert minimal_trait_model.disposition_ids == ("risk_tolerance",)


# ---------------------------------------------------------------------------
# Structural failures
# ---------------------------------------------------------------------------


def test_missing_required_field_fails_structurally(scratch_schema_dir: Path) -> None:
    data = deep_copy(minimal_traits_dict())
    del data["report"]
    write_bundle(scratch_schema_dir, traits=data)
    with pytest.raises(SchemaStructureError):
        _load(scratch_schema_dir)


# ---------------------------------------------------------------------------
# Semantic / cross-schema failures
# ---------------------------------------------------------------------------


def test_factor_schema_version_mismatch_rejected(minimal_taxonomy: FactorTaxonomy) -> None:
    data = deep_copy(minimal_traits_dict())
    data["factor_schema_version"] = 99
    with pytest.raises(SchemaConsistencyError, match="factor_schema_version"):
        parse_trait_model(data, minimal_taxonomy)


def test_weight_for_unknown_factor_rejected(minimal_taxonomy: FactorTaxonomy) -> None:
    data = deep_copy(minimal_traits_dict())
    data["importance_weights"]["traits"].append(
        {
            "factor": "not_a_real_factor",
            "prior": {"mu": 0.0, "sigma": 1.0},
            "self_report_reliability": "low",
        }
    )
    with pytest.raises(SchemaConsistencyError, match="unknown factor"):
        parse_trait_model(data, minimal_taxonomy)


def test_missing_weight_for_core_factor_rejected(minimal_taxonomy: FactorTaxonomy) -> None:
    data = deep_copy(minimal_traits_dict())
    data["importance_weights"]["traits"] = [
        t for t in data["importance_weights"]["traits"] if t["factor"] != "beta"
    ]
    with pytest.raises(SchemaConsistencyError, match="no importance weight"):
        parse_trait_model(data, minimal_taxonomy)


def test_duplicate_weight_for_same_factor_rejected(minimal_taxonomy: FactorTaxonomy) -> None:
    data = deep_copy(minimal_traits_dict())
    data["importance_weights"]["traits"].append(deep_copy(data["importance_weights"]["traits"][0]))
    with pytest.raises(SchemaValidationError, match="duplicate importance weight"):
        parse_trait_model(data, minimal_taxonomy)


def test_duplicate_disposition_id_rejected(minimal_taxonomy: FactorTaxonomy) -> None:
    data = deep_copy(minimal_traits_dict())
    data["dispositions"]["traits"].append(deep_copy(data["dispositions"]["traits"][0]))
    with pytest.raises(SchemaValidationError, match="duplicate disposition id"):
        parse_trait_model(data, minimal_taxonomy)


def test_wrong_tier_tag_rejected(minimal_taxonomy: FactorTaxonomy) -> None:
    data = deep_copy(minimal_traits_dict())
    # 'alpha' is a CORE factor; tagging its weight extended is a lie about the taxonomy.
    for weight in data["importance_weights"]["traits"]:
        if weight["factor"] == "alpha":
            weight["tier"] = "extended"
    with pytest.raises(SchemaValidationError, match="tier"):
        parse_trait_model(data, minimal_taxonomy)


def test_negative_sigma_rejected(minimal_taxonomy: FactorTaxonomy) -> None:
    data = deep_copy(minimal_traits_dict())
    data["importance_weights"]["traits"][0]["prior"]["sigma"] = -1.0
    with pytest.raises(ValidationError, match="sigma"):
        parse_trait_model(data, minimal_taxonomy)


def test_non_positive_beta_prior_rejected(minimal_taxonomy: FactorTaxonomy) -> None:
    data = deep_copy(minimal_traits_dict())
    data["dispositions"]["traits"][0]["prior"]["alpha"] = 0.0
    with pytest.raises(ValidationError, match="Beta parameters must be > 0"):
        parse_trait_model(data, minimal_taxonomy)


def test_non_latent_disposition_kind_rejected(minimal_taxonomy: FactorTaxonomy) -> None:
    data = deep_copy(minimal_traits_dict())
    data["dispositions"]["traits"][0]["kind"] = "observed"
    with pytest.raises(SchemaValidationError, match="latent"):
        parse_trait_model(data, minimal_taxonomy)


def test_wrong_posterior_kind_for_weights_rejected(minimal_taxonomy: FactorTaxonomy) -> None:
    data = deep_copy(minimal_traits_dict())
    data["importance_weights"]["posterior"] = "beta"  # weights must be 'normal'
    with pytest.raises(SchemaValidationError, match="must be 'normal'"):
        parse_trait_model(data, minimal_taxonomy)


def test_wrong_posterior_kind_for_dispositions_rejected(minimal_taxonomy: FactorTaxonomy) -> None:
    data = deep_copy(minimal_traits_dict())
    data["dispositions"]["posterior"] = "normal"  # dispositions must be 'beta'
    with pytest.raises(SchemaValidationError, match="must be 'beta'"):
        parse_trait_model(data, minimal_taxonomy)


def _load(schema_dir: Path) -> TraitModel:
    taxonomy = load_factor_taxonomy(schema_dir)
    return load_trait_model(schema_dir, taxonomy=taxonomy)
