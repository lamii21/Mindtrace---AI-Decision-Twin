"""Unit tests for ``simulation_repository``'s pure (de)serialization helpers (M10).

No database - ``SimulationModel`` is instantiated as a plain Python object,
never persisted. Covers what the integration suite cannot easily exercise:
a pre-M10 row whose ``synthesis`` column is genuinely ``NULL`` (``simulation``
is append-only at the DB-role level, so an integration test cannot mutate an
existing row to simulate this - see ``tests/integration/
test_api_simulate_ensemble.py``'s own module docstring).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from mindtrace.db.models.simulation import SimulationModel
from mindtrace.db.repositories.simulation_repository import (
    _model_to_simulation,
    _simulation_to_model,
)
from mindtrace.domain.confidence import ConfidenceResult
from mindtrace.domain.decision import FactorVector
from mindtrace.domain.enums import DecisionOutcome
from mindtrace.domain.ids import DecisionId, SimulationId, UserId
from mindtrace.domain.simulation import (
    ExtractionProvenance,
    Simulation,
    SimulationExtraction,
    SynthesisResult,
    TwinConfigResult,
)
from tests.support.twin_fixtures import twin_result_with

_FIXED_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _confidence() -> ConfidenceResult:
    return ConfidenceResult.model_validate(
        {
            "confidence_engine_version": "1",
            "confidence_config_version": "1",
            "value": 0.5,
            "raw": 0.5,
            "calibrated_output": False,
            "credible_interval": None,
            "inputs": {
                "evidence_sufficiency": 0.5,
                "n_bar": 1.0,
                "coverage": 1.0,
                "ensemble_disagreement": 0.1,
                "ensemble_term_capped": False,
                "historical_calibration": None,
                "calibrated": "false",
                "calibration_n": 0,
                "extraction_entropy": None,
                "extraction_path": "unavailable",
                "margin_adequacy": 1.0,
                "margin": 0.3,
            },
            "weights_used": {"A": 1.0},
        }
    )


def _extraction() -> SimulationExtraction:
    return SimulationExtraction(
        status="success",
        factors=FactorVector(readings={}),
        metadata=ExtractionProvenance(
            factor_schema_version=1,
            extraction_schema_version="1",
            prompt_version="1",
            provider="fake",
            model="fake",
            mode="single",
            temperature=0.0,
        ),
        failure_type=None,
        agreement=None,
    )


def _simulation(*, synthesis: SynthesisResult | None) -> Simulation:
    base = twin_result_with(twin="base", contributions={}, label=DecisionOutcome.ACCEPT)
    return Simulation(
        id=SimulationId(uuid4()),
        user_id=UserId(uuid4()),
        decision_id=DecisionId(uuid4()),
        simulation_version="1",
        scenario_content_hash="hash",
        extraction=_extraction(),
        twin_configs=(base,),
        synthesis=synthesis,
        model_confidence=_confidence(),
        created_at=_FIXED_NOW,
    )


class TestSynthesisRoundTrip:
    def test_a_populated_synthesis_round_trips(self) -> None:
        synthesis = SynthesisResult(
            recommended_label=DecisionOutcome.ACCEPT,
            margin=0.5,
            vote_tally={"ACCEPT": 2.0},
            label_consensus="unanimous",
            conflict_axis=(),
            synthesis_version="1",
        )
        simulation = _simulation(synthesis=synthesis)
        model = _simulation_to_model(simulation)
        assert model.synthesis == synthesis.model_dump(mode="json")

        reconstructed = _model_to_simulation(model)
        assert reconstructed.synthesis == synthesis

    def test_a_none_synthesis_round_trips_as_none(self) -> None:
        """A pre-M10 row: ``synthesis`` was never written, so the ORM column is ``NULL``."""
        simulation = _simulation(synthesis=None)
        model = _simulation_to_model(simulation)
        assert model.synthesis is None

        reconstructed = _model_to_simulation(model)
        assert reconstructed.synthesis is None

    def test_a_raw_pre_m10_row_object_with_no_synthesis_set_loads_as_none(self) -> None:
        """Mirrors what a genuinely pre-migration-0006 row looks like in memory: the ORM
        model's ``synthesis`` attribute is ``None`` (the column's own nullable default),
        never fabricated or backfilled."""
        simulation = _simulation(synthesis=None)
        model = _simulation_to_model(simulation)
        raw_row = SimulationModel(
            id=model.id,
            user_id=model.user_id,
            decision_id=model.decision_id,
            simulation_version=model.simulation_version,
            scenario_content_hash=model.scenario_content_hash,
            extraction=model.extraction,
            twin_configs=model.twin_configs,
            model_confidence=model.model_confidence,
            created_at=model.created_at,
            # `synthesis` deliberately omitted - exactly what a row inserted
            # before migration 0006 existed would look like once reloaded.
        )
        reconstructed = _model_to_simulation(raw_row)
        assert reconstructed.synthesis is None
        assert isinstance(reconstructed.twin_configs[0], TwinConfigResult)
