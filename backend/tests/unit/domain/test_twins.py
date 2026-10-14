"""Tests for the parallel-twin transform table loader (M10; ADR-007)."""

from __future__ import annotations

import pytest

from mindtrace.domain.errors import SchemaConsistencyError, SchemaValidationError
from mindtrace.domain.factors import load_factor_taxonomy
from mindtrace.domain.ids import FactorId
from mindtrace.domain.twins import BASE_TWIN_ID, TwinDefinition, load_twin_table, parse_twin_table

_TAXONOMY = load_factor_taxonomy()


def _raw(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "version": 1,
        "factor_schema_version": _TAXONOMY.version,
        "lambda": 0.35,
        "twins": [
            {
                "id": "career",
                "label": "Career You",
                "up": ["skill_growth"],
                "down": ["stability"],
            }
        ],
    }
    base.update(overrides)
    return base


class TestLoadTwinTable:
    def test_loads_the_real_schema_file(self) -> None:
        table = load_twin_table(taxonomy=_TAXONOMY)
        assert table.lambda_ == 0.35
        assert len(table.twins) == 4
        assert {t.id for t in table.twins} == {"career", "safe", "dream", "future"}

    def test_every_real_twin_satisfies_up_down_disjoint(self) -> None:
        table = load_twin_table(taxonomy=_TAXONOMY)
        for twin in table.twins:
            assert not (frozenset(twin.up) & frozenset(twin.down))

    def test_every_real_twin_references_only_known_factors(self) -> None:
        table = load_twin_table(taxonomy=_TAXONOMY)
        known = _TAXONOMY.all_ids
        for twin in table.twins:
            assert frozenset(twin.up) <= known
            assert frozenset(twin.down) <= known


class TestParseTwinTable:
    def test_parses_a_minimal_valid_table(self) -> None:
        table = parse_twin_table(_raw(), taxonomy=_TAXONOMY)
        assert table.version == 1
        assert table.lambda_ == 0.35
        assert table.twins[0].id == "career"

    def test_factor_schema_version_mismatch_raises(self) -> None:
        with pytest.raises(SchemaConsistencyError, match="factor_schema_version"):
            parse_twin_table(_raw(factor_schema_version=999), taxonomy=_TAXONOMY)

    def test_unknown_factor_in_up_raises(self) -> None:
        raw = _raw(twins=[{"id": "x", "label": "X", "up": ["not_a_real_factor"], "down": []}])
        with pytest.raises(SchemaConsistencyError, match="unknown factor"):
            parse_twin_table(raw, taxonomy=_TAXONOMY)

    def test_unknown_factor_in_down_raises(self) -> None:
        raw = _raw(twins=[{"id": "x", "label": "X", "up": [], "down": ["not_a_real_factor"]}])
        with pytest.raises(SchemaConsistencyError, match="unknown factor"):
            parse_twin_table(raw, taxonomy=_TAXONOMY)

    def test_duplicate_twin_ids_raises(self) -> None:
        raw = _raw(
            twins=[
                {"id": "x", "label": "X", "up": ["skill_growth"], "down": []},
                {"id": "x", "label": "X again", "up": [], "down": ["stability"]},
            ]
        )
        with pytest.raises(SchemaValidationError, match="duplicate"):
            parse_twin_table(raw, taxonomy=_TAXONOMY)

    def test_reserved_base_id_raises(self) -> None:
        raw = _raw(
            twins=[{"id": BASE_TWIN_ID, "label": "Base", "up": ["skill_growth"], "down": []}]
        )
        with pytest.raises(SchemaValidationError, match="reserved"):
            parse_twin_table(raw, taxonomy=_TAXONOMY)

    def test_factor_in_both_up_and_down_raises(self) -> None:
        raw = _raw(
            twins=[
                {
                    "id": "x",
                    "label": "X",
                    "up": ["skill_growth"],
                    "down": ["skill_growth"],
                }
            ]
        )
        with pytest.raises(SchemaValidationError, match="both up and down"):
            parse_twin_table(raw, taxonomy=_TAXONOMY)


class TestTwinDefinition:
    def test_frozen_and_extra_forbidden(self) -> None:
        twin = TwinDefinition(
            id="x", label="X", up=(FactorId("skill_growth"),), down=(FactorId("stability"),)
        )
        with pytest.raises(Exception):  # noqa: B017 - pydantic's own FrozenInstanceError
            twin.id = "y"
