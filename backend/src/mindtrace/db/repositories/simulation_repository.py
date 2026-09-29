"""Persistence for AG-7/AG-8's ``Simulation``/``Prediction`` (M7-scoped: base twin only).

:func:`persist_simulation` is the one place all four writes a completed
``/v1/simulate`` call produces - the ``Simulation`` row, its ``Prediction``,
its ``Evidence`` edge, and the ``Decision``'s transition to ``simulated`` -
happen inside a single ``user_scoped_session``. One session is one
transaction is one commit: either the whole graph becomes visible together,
or a failure partway through rolls all four back together (M7 planning s19).
Nothing here is encrypted (ADR-009) - see ``db/models/simulation.py``'s
module docstring for why every field is safe as plaintext.
"""

from __future__ import annotations

from sqlalchemy import select

from mindtrace.db.models.prediction import PredictionModel
from mindtrace.db.models.simulation import SimulationModel
from mindtrace.db.repositories import decision_repository
from mindtrace.db.repositories.evidence_repository import PostgresEvidenceStore
from mindtrace.db.session import user_scoped_session
from mindtrace.domain.confidence import ConfidenceResult
from mindtrace.domain.decision import Contribution
from mindtrace.domain.enums import DecisionOutcome, UncertainReason
from mindtrace.domain.evidence import Evidence
from mindtrace.domain.ids import DecisionId, PredictionId, SimulationId, UserId
from mindtrace.domain.simulation import (
    Prediction,
    Simulation,
    SimulationExtraction,
    TwinConfigResult,
)


def persist_simulation(
    *, simulation: Simulation, prediction: Prediction, evidence: Evidence, user_id: UserId
) -> None:
    """Atomically insert ``simulation``/``prediction``/``evidence``, mark the decision simulated.

    The explicit ``flush()`` between the ``simulation``/``prediction`` inserts
    matters: neither model declares an ORM ``relationship()`` to the other
    (both are plain FK columns), so SQLAlchemy's unit-of-work has no
    dependency information to order the two inserts by - without a flush,
    autoflush (triggered by ``mark_simulated``'s own ``session.get()`` below)
    can emit the ``prediction`` insert before the ``simulation`` row it
    references exists, violating the FK. Still one transaction, one commit -
    the flush does not end it.
    """
    with user_scoped_session(user_id) as session:
        session.add(_simulation_to_model(simulation))
        session.flush()
        session.add(_prediction_to_model(prediction, user_id=user_id))
        PostgresEvidenceStore(session, user_id=user_id).record(evidence)
        decision_repository.mark_simulated(session, decision_id=simulation.decision_id)


def get_simulation(
    user_id: UserId, simulation_id: SimulationId
) -> tuple[Simulation, Prediction] | None:
    """One simulation and its prediction, or ``None`` if not found / not visible (RLS)."""
    with user_scoped_session(user_id) as session:
        sim_row = session.get(SimulationModel, simulation_id)
        if sim_row is None:
            return None
        pred_row = session.execute(
            select(PredictionModel).where(PredictionModel.simulation_id == simulation_id)
        ).scalar_one()
        return _model_to_simulation(sim_row), _model_to_prediction(pred_row)


def list_simulations_for_decision(
    user_id: UserId, decision_id: DecisionId
) -> tuple[tuple[Simulation, Prediction], ...]:
    """Every simulation for ``decision_id``, newest first, each paired with its prediction."""
    with user_scoped_session(user_id) as session:
        sim_rows = (
            session.execute(
                select(SimulationModel)
                .where(SimulationModel.decision_id == decision_id)
                .order_by(SimulationModel.created_at.desc())
            )
            .scalars()
            .all()
        )
        pairs: list[tuple[Simulation, Prediction]] = []
        for sim_row in sim_rows:
            pred_row = session.execute(
                select(PredictionModel).where(PredictionModel.simulation_id == sim_row.id)
            ).scalar_one()
            pairs.append((_model_to_simulation(sim_row), _model_to_prediction(pred_row)))
        return tuple(pairs)


def _simulation_to_model(simulation: Simulation) -> SimulationModel:
    return SimulationModel(
        id=simulation.id,
        user_id=simulation.user_id,
        decision_id=simulation.decision_id,
        simulation_version=simulation.simulation_version,
        scenario_content_hash=simulation.scenario_content_hash,
        extraction=simulation.extraction.model_dump(mode="json"),
        twin_configs=[tc.model_dump(mode="json") for tc in simulation.twin_configs],
        model_confidence=simulation.model_confidence.model_dump(mode="json"),
        created_at=simulation.created_at,
    )


def _prediction_to_model(prediction: Prediction, *, user_id: UserId) -> PredictionModel:
    return PredictionModel(
        id=prediction.id,
        user_id=user_id,
        decision_id=prediction.decision_id,
        simulation_id=prediction.simulation_id,
        twin_version_id=prediction.twin_version_id,
        predicted_decision=prediction.predicted_decision.value,
        uncertain_reason=(
            prediction.uncertain_reason.value if prediction.uncertain_reason is not None else None
        ),
        predicted_confidence=prediction.predicted_confidence,
        credible_interval=prediction.credible_interval,
        factor_contributions=[c.model_dump(mode="json") for c in prediction.factor_contributions],
        margin=prediction.margin,
        engine_version=prediction.engine_version,
        created_at=prediction.created_at,
    )


def _model_to_simulation(row: SimulationModel) -> Simulation:
    return Simulation(
        id=SimulationId(row.id),
        user_id=UserId(row.user_id),
        decision_id=DecisionId(row.decision_id),
        simulation_version=row.simulation_version,
        scenario_content_hash=row.scenario_content_hash,
        extraction=SimulationExtraction.model_validate(row.extraction),
        twin_configs=tuple(TwinConfigResult.model_validate(tc) for tc in row.twin_configs),
        model_confidence=ConfidenceResult.model_validate(row.model_confidence),
        created_at=row.created_at,
    )


def _model_to_prediction(row: PredictionModel) -> Prediction:
    return Prediction(
        id=PredictionId(row.id),
        decision_id=DecisionId(row.decision_id),
        simulation_id=SimulationId(row.simulation_id),
        twin_version_id=None,
        predicted_decision=DecisionOutcome(row.predicted_decision),
        uncertain_reason=(
            UncertainReason(row.uncertain_reason) if row.uncertain_reason is not None else None
        ),
        predicted_confidence=row.predicted_confidence,
        credible_interval=None,
        factor_contributions=tuple(
            Contribution.model_validate(c) for c in row.factor_contributions
        ),
        margin=row.margin,
        engine_version=row.engine_version,
        created_at=row.created_at,
    )
