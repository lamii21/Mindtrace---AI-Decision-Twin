"""Shared fixtures for the MINDTRACE backend test suite."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from mindtrace.domain.factors import FactorTaxonomy, parse_factor_taxonomy
from mindtrace.domain.interview import InterviewBank, parse_interview_bank
from mindtrace.domain.schema_bundle import SchemaBundle, load_schema_bundle
from mindtrace.domain.traits import TraitModel, parse_trait_model
from tests.support.schema_factories import (
    REAL_SCHEMA_DIR,
    minimal_factors_dict,
    minimal_interview_dict,
    minimal_traits_dict,
)


@pytest.fixture(scope="session")
def real_schema_dir() -> Path:
    """The repository's real ``schema/`` directory."""
    return REAL_SCHEMA_DIR


@pytest.fixture(scope="session")
def real_bundle() -> SchemaBundle:
    """The real, checked-in schema bundle, loaded once per test session."""
    return load_schema_bundle(REAL_SCHEMA_DIR)


@pytest.fixture
def minimal_taxonomy() -> FactorTaxonomy:
    """A small, valid, self-contained :class:`FactorTaxonomy`."""
    return parse_factor_taxonomy(minimal_factors_dict())


@pytest.fixture
def minimal_trait_model(minimal_taxonomy: FactorTaxonomy) -> TraitModel:
    """A small, valid :class:`TraitModel` over :func:`minimal_taxonomy`."""
    return parse_trait_model(minimal_traits_dict(), minimal_taxonomy)


@pytest.fixture
def minimal_interview_bank(
    minimal_taxonomy: FactorTaxonomy, minimal_trait_model: TraitModel
) -> InterviewBank:
    """A small, valid :class:`InterviewBank` over the minimal taxonomy/trait model."""
    return parse_interview_bank(
        minimal_interview_dict(), taxonomy=minimal_taxonomy, trait_model=minimal_trait_model
    )


@pytest.fixture
def scratch_schema_dir(tmp_path: Path) -> Iterator[Path]:
    """An empty directory a test can populate with :func:`write_bundle`."""
    directory = tmp_path / "schema"
    directory.mkdir()
    yield directory
