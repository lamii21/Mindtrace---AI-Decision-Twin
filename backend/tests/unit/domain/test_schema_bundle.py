"""Tests for the cross-schema bundle loader (``mindtrace.domain.schema_bundle``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mindtrace.domain.errors import SchemaConsistencyError
from mindtrace.domain.factors import parse_factor_taxonomy
from mindtrace.domain.interview import parse_interview_bank
from mindtrace.domain.schema_bundle import SchemaBundle, load_schema_bundle
from mindtrace.domain.traits import parse_trait_model
from tests.support.schema_factories import (
    deep_copy,
    minimal_factors_dict,
    minimal_interview_dict,
    minimal_traits_dict,
    write_bundle,
)


def test_real_bundle_loads_and_cross_validates(real_bundle: SchemaBundle) -> None:
    assert real_bundle.schema_version == 1
    assert real_bundle.factors.version == real_bundle.traits.factor_schema_version
    assert real_bundle.factors.version == real_bundle.interview.factor_schema_version


def test_minimal_bundle_round_trips(scratch_schema_dir: Path) -> None:
    write_bundle(scratch_schema_dir)
    bundle = load_schema_bundle(scratch_schema_dir)
    assert bundle.schema_version == 1
    assert bundle.factors.core_ids == ("alpha", "beta")


def test_traits_version_mismatch_surfaces_through_the_bundle(scratch_schema_dir: Path) -> None:
    traits = deep_copy(minimal_traits_dict())
    traits["factor_schema_version"] = 7
    write_bundle(scratch_schema_dir, traits=traits)
    with pytest.raises(SchemaConsistencyError, match="factor_schema_version"):
        load_schema_bundle(scratch_schema_dir)


def test_interview_version_mismatch_surfaces_through_the_bundle(scratch_schema_dir: Path) -> None:
    interview = deep_copy(minimal_interview_dict())
    interview["factor_schema_version"] = 7
    write_bundle(scratch_schema_dir, interview=interview)
    with pytest.raises(SchemaConsistencyError, match="factor_schema_version"):
        load_schema_bundle(scratch_schema_dir)


def test_bundle_rejects_pieces_individually_valid_but_mutually_inconsistent() -> None:
    """The version-agreement invariant is enforced by ``SchemaBundle`` itself.

    Each piece below is independently valid against the taxonomy it was loaded
    against - ``load_schema_bundle`` never sees this combination, since it
    always loads all three against one shared taxonomy. This proves the
    invariant holds even if a future caller assembles a bundle from pieces
    loaded separately (e.g. from different sources or at different times).
    """
    taxonomy_v1 = parse_factor_taxonomy(minimal_factors_dict())
    interview_v1 = parse_interview_bank(
        minimal_interview_dict(),
        taxonomy=taxonomy_v1,
        trait_model=parse_trait_model(minimal_traits_dict(), taxonomy_v1),
    )

    factors_v2_data = deep_copy(minimal_factors_dict())
    factors_v2_data["version"] = 2
    taxonomy_v2 = parse_factor_taxonomy(factors_v2_data)
    traits_v2_data = deep_copy(minimal_traits_dict())
    traits_v2_data["factor_schema_version"] = 2
    traits_v2 = parse_trait_model(traits_v2_data, taxonomy_v2)  # valid against taxonomy_v2

    with pytest.raises(SchemaConsistencyError, match="disagree"):
        SchemaBundle(factors=taxonomy_v1, traits=traits_v2, interview=interview_v1)
