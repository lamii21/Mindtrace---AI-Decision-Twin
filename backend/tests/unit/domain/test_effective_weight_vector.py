"""Construction-time invariants of `EffectiveWeightVector` and
`TraitModel.core_weight_factor_ids` (M6-A)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mindtrace.domain.decision import DispositionInputs, WeightVector
from mindtrace.domain.enums import FactorTier
from mindtrace.domain.ids import FactorId
from mindtrace.domain.traits import EffectiveWeightVector
from tests.support.preference_fixtures import TRAIT_MODEL


class TestCoreWeightFactorIds:
    def test_excludes_extended_factors(self) -> None:
        core_ids = set(TRAIT_MODEL.core_weight_factor_ids)
        extended_specs = [w for w in TRAIT_MODEL.weights if w.tier is FactorTier.EXTENDED]
        assert extended_specs  # sanity: the schema really does have extended weights
        for spec in extended_specs:
            assert spec.factor not in core_ids

    def test_matches_every_core_tier_weight(self) -> None:
        expected = {w.factor for w in TRAIT_MODEL.weights if w.tier is FactorTier.CORE}
        assert set(TRAIT_MODEL.core_weight_factor_ids) == expected

    def test_is_a_subset_of_weight_factor_ids(self) -> None:
        assert set(TRAIT_MODEL.core_weight_factor_ids) <= TRAIT_MODEL.weight_factor_ids

    def test_has_sixteen_core_factors(self) -> None:
        assert len(TRAIT_MODEL.core_weight_factor_ids) == 16

    def test_is_deterministic_file_order(self) -> None:
        assert TRAIT_MODEL.core_weight_factor_ids == TRAIT_MODEL.core_weight_factor_ids


class TestEffectiveWeightVector:
    def _weights(self) -> WeightVector:
        return WeightVector(weights={FactorId("skill_growth"): 1.0})

    def _dispositions(self) -> DispositionInputs:
        return DispositionInputs.neutral()

    def _build(self, **overrides: object) -> EffectiveWeightVector:
        base = {
            "weights": self._weights(),
            "dispositions": self._dispositions(),
            "trait_schema_version": 1,
            "preference_engine_version": "1",
            "projection_version": "1",
            "read_transform": "softmax_over_known",
            "total_weight_evidence_count": 0,
            "total_disposition_evidence_count": 0,
        }
        base.update(overrides)
        return EffectiveWeightVector(**base)  # type: ignore[arg-type]

    def test_valid_snapshot_is_accepted(self) -> None:
        snapshot = self._build()
        assert snapshot.trait_schema_version == 1

    def test_is_frozen(self) -> None:
        snapshot = self._build()
        with pytest.raises(ValidationError):
            snapshot.trait_schema_version = 2

    def test_negative_weight_evidence_count_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._build(total_weight_evidence_count=-1)

    def test_negative_disposition_evidence_count_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._build(total_disposition_evidence_count=-1)

    def test_extra_field_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._build(extra_field="not allowed")
