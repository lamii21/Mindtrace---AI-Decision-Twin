"""Tests for the factor taxonomy loader/parser (``mindtrace.domain.factors``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mindtrace.domain.enums import FactorDirection, FactorTier, ScaleLevel
from mindtrace.domain.errors import SchemaStructureError, SchemaValidationError
from mindtrace.domain.factors import FactorTaxonomy, load_factor_taxonomy, parse_factor_taxonomy
from mindtrace.domain.schema_bundle import SchemaBundle
from tests.support.schema_factories import deep_copy, minimal_factors_dict, write_bundle

# ---------------------------------------------------------------------------
# Happy path: the real, checked-in taxonomy
# ---------------------------------------------------------------------------


class TestRealTaxonomy:
    def test_loads(self, real_schema_dir: Path) -> None:
        taxonomy = load_factor_taxonomy(real_schema_dir)
        assert isinstance(taxonomy, FactorTaxonomy)

    def test_has_sixteen_core_factors(self, real_bundle: SchemaBundle) -> None:
        assert len(real_bundle.factors.core) == 16

    def test_has_three_extended_factors(self, real_bundle: SchemaBundle) -> None:
        assert len(real_bundle.factors.extended) == 3

    def test_every_core_factor_has_examples_and_evidence(self, real_bundle: SchemaBundle) -> None:
        for factor in real_bundle.factors.core:
            assert factor.examples, factor.id
            assert factor.possible_evidence, factor.id

    def test_anchors_strictly_increase_for_every_factor(self, real_bundle: SchemaBundle) -> None:
        for factor in real_bundle.factors.all_factors:
            ordered = sorted(factor.anchors.items(), key=lambda kv: kv[0].rank)
            values = [v for _, v in ordered]
            assert values == sorted(values), factor.id
            assert len(set(values)) == len(values), f"{factor.id} has repeated anchor values"

    def test_only_two_factors_override_anchors(self, real_bundle: SchemaBundle) -> None:
        overridden = {f.id for f in real_bundle.factors.all_factors if f.has_anchor_override}
        assert overridden == {"financial_return", "downside_risk"}

    def test_direction_is_always_benefit_or_cost(self, real_bundle: SchemaBundle) -> None:
        for factor in real_bundle.factors.all_factors:
            assert factor.direction in (FactorDirection.BENEFIT, FactorDirection.COST)

    def test_cost_factors_are_exactly_time_demand_and_downside_risk(
        self, real_bundle: SchemaBundle
    ) -> None:
        all_factors = real_bundle.factors.all_factors
        costs = {f.id for f in all_factors if f.direction is FactorDirection.COST}
        assert costs == {"time_demand", "downside_risk"}

    def test_get_and_contains(self, real_bundle: SchemaBundle) -> None:
        taxonomy = real_bundle.factors
        assert "skill_growth" in taxonomy
        assert taxonomy.get("skill_growth").label == "Skill growth"
        assert "not_a_real_factor" not in taxonomy
        with pytest.raises(KeyError):
            taxonomy.get("not_a_real_factor")


# ---------------------------------------------------------------------------
# Minimal fixture: happy path
# ---------------------------------------------------------------------------


def test_minimal_fixture_parses(minimal_taxonomy: FactorTaxonomy) -> None:
    assert minimal_taxonomy.core_ids == ("alpha", "beta")
    assert minimal_taxonomy.get("gamma").tier is FactorTier.EXTENDED
    assert minimal_taxonomy.get("alpha").anchor_for(ScaleLevel.VERY_HIGH) == 1.0


# ---------------------------------------------------------------------------
# Structural failures (caught by the JSON Schema, via load_factor_taxonomy)
# ---------------------------------------------------------------------------


def test_missing_required_field_fails_structurally(scratch_schema_dir: Path) -> None:
    data = deep_copy(minimal_factors_dict())
    del data["factors"][0]["direction"]
    write_bundle(scratch_schema_dir, factors=data)
    with pytest.raises(SchemaStructureError, match="direction"):
        load_factor_taxonomy(scratch_schema_dir)


def test_bad_direction_enum_fails_structurally(scratch_schema_dir: Path) -> None:
    data = deep_copy(minimal_factors_dict())
    data["factors"][0]["direction"] = "upward"
    write_bundle(scratch_schema_dir, factors=data)
    with pytest.raises(SchemaStructureError):
        load_factor_taxonomy(scratch_schema_dir)


def test_extra_unknown_field_fails_structurally(scratch_schema_dir: Path) -> None:
    data = deep_copy(minimal_factors_dict())
    data["factors"][0]["totally_made_up_field"] = 123
    write_bundle(scratch_schema_dir, factors=data)
    with pytest.raises(SchemaStructureError):
        load_factor_taxonomy(scratch_schema_dir)


def test_malformed_yaml_reports_the_file_and_is_actionable(scratch_schema_dir: Path) -> None:
    write_bundle(scratch_schema_dir)
    (scratch_schema_dir / "factors.yaml").write_text("factors: [unclosed", encoding="utf-8")
    with pytest.raises(SchemaStructureError) as excinfo:
        load_factor_taxonomy(scratch_schema_dir)
    message = str(excinfo.value)
    assert "factors.yaml" in message
    assert "invalid YAML" in message


def test_malformed_json_schema_file_reports_the_file_and_is_actionable(
    scratch_schema_dir: Path,
) -> None:
    write_bundle(scratch_schema_dir)
    (scratch_schema_dir / "factors.schema.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SchemaStructureError) as excinfo:
        load_factor_taxonomy(scratch_schema_dir)
    message = str(excinfo.value)
    assert "factors.schema.json" in message
    assert "invalid JSON" in message


# ---------------------------------------------------------------------------
# Semantic failures (caught by parse_factor_taxonomy)
# ---------------------------------------------------------------------------


def test_duplicate_factor_id_rejected() -> None:
    data = deep_copy(minimal_factors_dict())
    data["factors"].append(deep_copy(data["factors"][0]))
    with pytest.raises(SchemaValidationError, match="duplicate factor id"):
        parse_factor_taxonomy(data)


def test_duplicate_id_across_core_and_extended_rejected() -> None:
    data = deep_copy(minimal_factors_dict())
    data["extended_factors"][0]["id"] = "alpha"
    with pytest.raises(SchemaValidationError, match="duplicate factor id"):
        parse_factor_taxonomy(data)


def test_direction_better_mismatch_rejected() -> None:
    data = deep_copy(minimal_factors_dict())
    data["factors"][0]["direction"] = "benefit"
    data["factors"][0]["better"] = "lower"
    with pytest.raises(SchemaValidationError, match="better"):
        parse_factor_taxonomy(data)


def test_non_increasing_anchors_rejected() -> None:
    data = deep_copy(minimal_factors_dict())
    data["factors"][0]["anchors"] = {
        "very_low": 0.0,
        "low": 0.5,
        "moderate": 0.4,  # decreases - invalid
        "high": 0.75,
        "very_high": 1.0,
    }
    with pytest.raises(SchemaValidationError, match="strictly increase"):
        parse_factor_taxonomy(data)


def test_anchors_missing_a_level_rejected() -> None:
    data = deep_copy(minimal_factors_dict())
    data["factors"][0]["anchors"] = {"very_low": 0.0, "low": 0.5, "high": 0.75, "very_high": 1.0}
    with pytest.raises(SchemaValidationError, match="missing levels"):
        parse_factor_taxonomy(data)


def test_anchor_out_of_bounds_rejected() -> None:
    data = deep_copy(minimal_factors_dict())
    data["factors"][0]["anchors"] = {
        "very_low": 0.0,
        "low": 0.25,
        "moderate": 0.5,
        "high": 0.75,
        "very_high": 1.2,  # out of [0, 1]
    }
    with pytest.raises(SchemaValidationError, match=r"outside \[0, 1\]"):
        parse_factor_taxonomy(data)


def test_descending_range_rejected() -> None:
    data = deep_copy(minimal_factors_dict())
    data["factors"][0]["range"] = ["very_high", "very_low"]
    with pytest.raises(SchemaValidationError, match="descending"):
        parse_factor_taxonomy(data)


def test_scale_default_anchors_missing_level_rejected() -> None:
    data = deep_copy(minimal_factors_dict())
    del data["scale"]["default_anchors"]["moderate"]
    with pytest.raises(SchemaValidationError, match="every scale level"):
        parse_factor_taxonomy(data)


def test_anchor_key_not_a_scale_level_rejected() -> None:
    # The JSON Schema only constrains anchor *values*, not key names, so this
    # must be caught by the pure parser.
    data = deep_copy(minimal_factors_dict())
    data["factors"][0]["anchors"] = {
        "vry_low": 0.0,  # typo: not a real ScaleLevel
        "low": 0.25,
        "moderate": 0.5,
        "high": 0.75,
        "very_high": 1.0,
    }
    with pytest.raises(SchemaValidationError, match="not a scale level"):
        parse_factor_taxonomy(data)
