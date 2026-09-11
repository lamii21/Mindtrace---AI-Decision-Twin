"""Tests for the Twin Interview bank loader/parser (``mindtrace.domain.interview``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mindtrace.domain.errors import (
    SchemaConsistencyError,
    SchemaStructureError,
    SchemaValidationError,
)
from mindtrace.domain.factors import FactorTaxonomy, load_factor_taxonomy
from mindtrace.domain.interview import InterviewBank, load_interview_bank, parse_interview_bank
from mindtrace.domain.schema_bundle import SchemaBundle
from mindtrace.domain.traits import TraitModel, load_trait_model
from tests.support.schema_factories import (
    REAL_SCHEMA_DIR,
    deep_copy,
    minimal_interview_dict,
    write_bundle,
)

# ---------------------------------------------------------------------------
# Happy path: the real, checked-in item bank
# ---------------------------------------------------------------------------


class TestRealInterviewBank:
    def test_loads(self, real_bundle: SchemaBundle) -> None:
        bank = load_interview_bank(
            REAL_SCHEMA_DIR, taxonomy=real_bundle.factors, trait_model=real_bundle.traits
        )
        assert isinstance(bank, InterviewBank)

    def test_item_count(self, real_bundle: SchemaBundle) -> None:
        assert len(real_bundle.interview.pairwise) == 16  # 14 + 2 consistency repeats
        assert len(real_bundle.interview.disposition) == 8

    def test_all_item_ids_unique(self, real_bundle: SchemaBundle) -> None:
        ids = real_bundle.interview.item_ids
        assert len(ids) == len(set(ids))

    def test_consistency_checks_are_p03r_and_p07r(self, real_bundle: SchemaBundle) -> None:
        assert set(real_bundle.interview.config.consistency_check_item_ids) == {"p03r", "p07r"}

    def test_every_disposition_has_exactly_two_items(self, real_bundle: SchemaBundle) -> None:
        by_target: dict[str, int] = {}
        for item in real_bundle.interview.disposition:
            by_target[item.target] = by_target.get(item.target, 0) + 1
        assert by_target == {
            "risk_tolerance": 2,
            "time_discount": 2,
            "ambiguity_aversion": 2,
            "effort_tolerance": 2,
        }

    def test_every_core_factor_is_covered_by_the_fixed_prefix(
        self, real_bundle: SchemaBundle
    ) -> None:
        prefix_ids = {f"p{n:02d}" for n in range(1, 13)}  # p01..p12, the fixed_prefix_items
        covered: set[str] = set()
        for item in real_bundle.interview.pairwise:
            if item.id in prefix_ids:
                covered |= set(item.covers)
        assert covered >= set(real_bundle.factors.core_ids)


# ---------------------------------------------------------------------------
# Minimal fixture
# ---------------------------------------------------------------------------


def test_minimal_fixture_parses(minimal_interview_bank: InterviewBank) -> None:
    assert minimal_interview_bank.total_items == 3
    assert minimal_interview_bank.pairwise[0].varied_factors == {"alpha"}


# ---------------------------------------------------------------------------
# Structural failures
# ---------------------------------------------------------------------------


def test_missing_required_field_fails_structurally(scratch_schema_dir: Path) -> None:
    data = deep_copy(minimal_interview_dict())
    del data["pairwise"][0]["covers"]
    write_bundle(scratch_schema_dir, interview=data)
    with pytest.raises(SchemaStructureError):
        _load(scratch_schema_dir)


def test_gamble_item_missing_risky_option_fails_structurally(scratch_schema_dir: Path) -> None:
    data = deep_copy(minimal_interview_dict())
    del data["disposition"][0]["risky_option"]
    write_bundle(scratch_schema_dir, interview=data)
    with pytest.raises(SchemaStructureError):
        _load(scratch_schema_dir)


def test_bad_level_code_fails_structurally(scratch_schema_dir: Path) -> None:
    data = deep_copy(minimal_interview_dict())
    data["pairwise"][0]["A"]["alpha"] = "very_high"  # must be the short code 'vh'
    write_bundle(scratch_schema_dir, interview=data)
    with pytest.raises(SchemaStructureError):
        _load(scratch_schema_dir)


# ---------------------------------------------------------------------------
# Semantic / cross-schema failures
# ---------------------------------------------------------------------------


def test_factor_schema_version_mismatch_rejected(
    minimal_taxonomy: FactorTaxonomy, minimal_trait_model: TraitModel
) -> None:
    data = deep_copy(minimal_interview_dict())
    data["factor_schema_version"] = 42
    with pytest.raises(SchemaConsistencyError, match="factor_schema_version"):
        parse_interview_bank(data, taxonomy=minimal_taxonomy, trait_model=minimal_trait_model)


def test_unknown_factor_reference_rejected(
    minimal_taxonomy: FactorTaxonomy, minimal_trait_model: TraitModel
) -> None:
    data = deep_copy(minimal_interview_dict())
    # Keep 'covers' internally consistent with the profiles (alpha + not_a_factor) so the
    # covers-consistency check passes and the unknown-factor cross-check is what fires.
    data["pairwise"][0]["A"] = {"not_a_factor": "h", "alpha": "h"}
    data["pairwise"][0]["covers"] = ["not_a_factor", "alpha"]
    with pytest.raises(SchemaConsistencyError, match="unknown factor"):
        parse_interview_bank(data, taxonomy=minimal_taxonomy, trait_model=minimal_trait_model)


def test_covers_mismatch_rejected(
    minimal_taxonomy: FactorTaxonomy, minimal_trait_model: TraitModel
) -> None:
    data = deep_copy(minimal_interview_dict())
    data["pairwise"][0]["covers"] = ["alpha", "beta"]  # profiles only vary 'alpha'
    with pytest.raises(SchemaValidationError, match="covers"):
        parse_interview_bank(data, taxonomy=minimal_taxonomy, trait_model=minimal_trait_model)


def test_unknown_disposition_target_rejected(
    minimal_taxonomy: FactorTaxonomy, minimal_trait_model: TraitModel
) -> None:
    data = deep_copy(minimal_interview_dict())
    data["disposition"][0]["target"] = "not_a_disposition"
    with pytest.raises(SchemaConsistencyError, match="unknown disposition"):
        parse_interview_bank(data, taxonomy=minimal_taxonomy, trait_model=minimal_trait_model)


def test_duplicate_item_id_across_pairwise_and_disposition_rejected(
    minimal_taxonomy: FactorTaxonomy, minimal_trait_model: TraitModel
) -> None:
    data = deep_copy(minimal_interview_dict())
    data["disposition"][0]["id"] = "p01"  # collides with a pairwise item id
    with pytest.raises(SchemaValidationError, match="duplicate interview item id"):
        parse_interview_bank(data, taxonomy=minimal_taxonomy, trait_model=minimal_trait_model)


def test_identical_pairwise_items_rejected(
    minimal_taxonomy: FactorTaxonomy, minimal_trait_model: TraitModel
) -> None:
    data = deep_copy(minimal_interview_dict())
    duplicate = deep_copy(data["pairwise"][0])
    duplicate["id"] = "p99"
    data["pairwise"].append(duplicate)
    with pytest.raises(SchemaValidationError, match="identical"):
        parse_interview_bank(data, taxonomy=minimal_taxonomy, trait_model=minimal_trait_model)


def test_consistency_check_referencing_unknown_item_rejected(
    minimal_taxonomy: FactorTaxonomy, minimal_trait_model: TraitModel
) -> None:
    data = deep_copy(minimal_interview_dict())
    data["config"]["consistency_check_item_ids"] = ["does_not_exist"]
    with pytest.raises(SchemaValidationError, match="unknown pairwise item"):
        parse_interview_bank(data, taxonomy=minimal_taxonomy, trait_model=minimal_trait_model)


def test_consistency_check_pointing_at_non_flagged_item_rejected(
    minimal_taxonomy: FactorTaxonomy, minimal_trait_model: TraitModel
) -> None:
    data = deep_copy(minimal_interview_dict())
    data["config"]["consistency_check_item_ids"] = ["p01"]  # p01 has no role: consistency_check
    with pytest.raises(SchemaValidationError, match="role"):
        parse_interview_bank(data, taxonomy=minimal_taxonomy, trait_model=minimal_trait_model)


def test_fixed_prefix_exceeding_item_count_rejected(
    minimal_taxonomy: FactorTaxonomy, minimal_trait_model: TraitModel
) -> None:
    data = deep_copy(minimal_interview_dict())
    data["config"]["fixed_prefix_items"] = 999
    with pytest.raises(SchemaValidationError, match="fixed_prefix_items"):
        parse_interview_bank(data, taxonomy=minimal_taxonomy, trait_model=minimal_trait_model)


def test_mismatched_item_type_and_keyed_field_rejected(
    minimal_taxonomy: FactorTaxonomy, minimal_trait_model: TraitModel
) -> None:
    data = deep_copy(minimal_interview_dict())
    data["disposition"][0]["type"] = "effort"  # keyed field is still risky_option (gamble)
    with pytest.raises(SchemaValidationError, match="does not match"):
        parse_interview_bank(data, taxonomy=minimal_taxonomy, trait_model=minimal_trait_model)


def test_disposition_item_with_two_keyed_fields_rejected(
    minimal_taxonomy: FactorTaxonomy, minimal_trait_model: TraitModel
) -> None:
    # The JSON Schema requires the keyed field matching `type` but never forbids extras,
    # so this must be caught by the pure parser, not just structurally.
    data = deep_copy(minimal_interview_dict())
    data["disposition"][0]["patient_option"] = "A"  # alongside the existing risky_option
    with pytest.raises(SchemaValidationError, match="exactly one of"):
        parse_interview_bank(data, taxonomy=minimal_taxonomy, trait_model=minimal_trait_model)


def test_bad_level_code_rejected_by_pure_parser(
    minimal_taxonomy: FactorTaxonomy, minimal_trait_model: TraitModel
) -> None:
    # Same fault as test_bad_level_code_fails_structurally, but bypassing the JSON Schema
    # layer to prove the pure parser also guards it independently.
    data = deep_copy(minimal_interview_dict())
    data["pairwise"][0]["A"]["alpha"] = "xx"
    with pytest.raises(SchemaValidationError, match="unknown level code"):
        parse_interview_bank(data, taxonomy=minimal_taxonomy, trait_model=minimal_trait_model)


def test_target_total_descending_rejected(
    minimal_taxonomy: FactorTaxonomy, minimal_trait_model: TraitModel
) -> None:
    data = deep_copy(minimal_interview_dict())
    data["config"]["target_total"] = [2, 1]
    with pytest.raises(SchemaValidationError, match="descending"):
        parse_interview_bank(data, taxonomy=minimal_taxonomy, trait_model=minimal_trait_model)


def test_target_total_max_exceeding_item_count_rejected(
    minimal_taxonomy: FactorTaxonomy, minimal_trait_model: TraitModel
) -> None:
    data = deep_copy(minimal_interview_dict())
    data["config"]["target_total"] = [1, 999]
    with pytest.raises(SchemaValidationError, match="target_total max"):
        parse_interview_bank(data, taxonomy=minimal_taxonomy, trait_model=minimal_trait_model)


def _load(schema_dir: Path) -> InterviewBank:
    taxonomy = load_factor_taxonomy(schema_dir)
    trait_model = load_trait_model(schema_dir, taxonomy=taxonomy)
    return load_interview_bank(schema_dir, taxonomy=taxonomy, trait_model=trait_model)
