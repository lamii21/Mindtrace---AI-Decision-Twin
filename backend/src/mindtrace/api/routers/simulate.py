"""``POST /v1/simulate`` + ``GET /v1/simulations/{id}`` (``docs/api/08`` s5, M7).

**Idempotency (M7 planning s20).** Unlike ``/v1/memories``/``/v1/decisions``
(M6, check-existing-then-create-then-claim), this reserves the
``Idempotency-Key`` claim *before* running the expensive orchestration/LLM
call, using a pre-allocated ``simulation_id`` as the claimed resource:

1. Validate the decision first (``decision_service.
   validate_decision_for_simulation``) - a bad ``decision_id``/an archived
   decision fails immediately, *before* any claim exists, so it can never
   burn a key on a request that was never going to succeed.
2. Claim the key with a fresh, pre-generated ``simulation_id``. Win ->
   compute using that id. Lose -> another request already claimed this key;
   if its simulation has already finished, replay it; if not (a genuinely
   concurrent request still computing), return a plain, honest 409
   (``SimulationInProgressError``) rather than either blocking or silently
   running a second LLM call.

This makes duplicate LLM calls for the *same* key structurally
impossible for a sequential retry, and bounds the residual concurrent-race
window to "the caller sees a 409 and retries" rather than "a second
simulation silently runs" (M6's own documented residual, tightened here).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, status

from mindtrace.api.deps import get_current_user_id, get_key_provider, get_llm_client, now
from mindtrace.api.idempotency import fingerprint
from mindtrace.api.schemas.simulation import (
    ConfidenceInputsOut,
    ConfidenceOut,
    ContributionOut,
    DecisionSummaryOut,
    SimulateRequest,
    SimulationOut,
    TraceEdgeOut,
    TraceGraphOut,
    TraceNodeOut,
    TwinResultOut,
)
from mindtrace.db.crypto import KeyProvider
from mindtrace.domain.confidence import ConfidenceResult
from mindtrace.domain.decision import Contribution
from mindtrace.domain.evidence import Evidence
from mindtrace.domain.ids import DecisionId, SimulationId, UserId
from mindtrace.domain.simulation import Prediction, Simulation
from mindtrace.llm.client import LLMClient
from mindtrace.services import decision_service, idempotency_service
from mindtrace.services.errors import (
    IdempotencyKeyConflictError,
    ResourceNotFoundError,
    SimulationInProgressError,
)

router = APIRouter(tags=["simulate"])

_ROUTE_CREATE = "POST /v1/simulate"


@router.post("/simulate", response_model=SimulationOut, status_code=status.HTTP_200_OK)
def create_simulation(
    body: SimulateRequest,
    user_id: UserId = Depends(get_current_user_id),
    key_provider: KeyProvider = Depends(get_key_provider),
    llm_client: LLMClient = Depends(get_llm_client),
    request_time: datetime = Depends(now),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> SimulationOut:
    """Run one simulation for ``body.decision_id`` and persist it."""
    decision_id = DecisionId(body.decision_id)
    fp = fingerprint(body.model_dump(mode="json"))

    decision = decision_service.validate_decision_for_simulation(
        user_id, decision_id, key_provider=key_provider
    )

    if idempotency_key is None:
        simulation, prediction = decision_service.run_simulation(
            decision, llm_client=llm_client, now=request_time
        )
        return to_simulation_out(user_id, simulation, prediction)

    reserved_id = SimulationId(uuid4())
    claim = idempotency_service.claim_or_replay(
        user_id=user_id,
        route=_ROUTE_CREATE,
        idempotency_key=idempotency_key,
        request_fingerprint=fp,
        resource_id=UUID(str(reserved_id)),
        response_status=status.HTTP_200_OK,
        now=request_time,
    )
    if not claim.claimed:
        assert claim.existing is not None
        if claim.existing.request_fingerprint != fp:
            msg = "Idempotency-Key reused with a different request body"
            raise IdempotencyKeyConflictError(msg)
        won_id = SimulationId(claim.existing.resource_id)
        try:
            simulation, prediction = decision_service.get_simulation(user_id, won_id)
        except ResourceNotFoundError:
            # The winner claimed the key but has not finished persisting yet
            # (a genuinely concurrent race, not a sequential retry) - report
            # it plainly rather than blocking or running a second LLM call.
            msg = "a simulation for this Idempotency-Key is already in progress"
            raise SimulationInProgressError(msg) from None
        return to_simulation_out(user_id, simulation, prediction)

    simulation, prediction = decision_service.run_simulation(
        decision, llm_client=llm_client, now=request_time, simulation_id=reserved_id
    )
    return to_simulation_out(user_id, simulation, prediction)


@router.get("/simulations/{simulation_id}", response_model=SimulationOut)
def get_simulation(
    simulation_id: UUID, user_id: UserId = Depends(get_current_user_id)
) -> SimulationOut:
    """Return one of the caller's own simulations."""
    simulation, prediction = decision_service.get_simulation(user_id, SimulationId(simulation_id))
    return to_simulation_out(user_id, simulation, prediction)


def to_simulation_out(
    user_id: UserId, simulation: Simulation, prediction: Prediction
) -> SimulationOut:
    """Assemble the response DTO for both the create and retrieval routes."""
    base = simulation.twin_configs[0]  # exactly one, "base", in M7
    decision_result = base.decision
    contributions = [_to_contribution_out(c) for c in decision_result.contributions]
    evidence = decision_service.list_evidence_for_simulation(user_id, simulation.id)

    return SimulationOut(
        simulation_id=simulation.id,
        decision_id=simulation.decision_id,
        engine_version=simulation.simulation_version,
        factor_schema_version=simulation.extraction.metadata.factor_schema_version,
        twin_version_id=prediction.twin_version_id,
        decision=DecisionSummaryOut(
            label=prediction.predicted_decision.value,
            uncertain_reason=(
                prediction.uncertain_reason.value
                if prediction.uncertain_reason is not None
                else None
            ),
            score=decision_result.score,
            margin=decision_result.margin,
            coverage=decision_result.coverage,
        ),
        confidence=_to_confidence_out(simulation.model_confidence),
        contributions=contributions,
        trace=_build_trace(simulation, evidence),
        per_twin=[
            TwinResultOut(
                twin=base.twin,
                label=decision_result.label.value,
                score=decision_result.score,
                top_contributions=contributions,
            )
        ],
        synthesis=None,
        debate=None,
        elicitation_hint=None,
        created_at=simulation.created_at,
    )


def _to_contribution_out(contribution: Contribution) -> ContributionOut:
    return ContributionOut(
        factor_id=str(contribution.factor_id),
        level_a=contribution.level_a.value,
        weight=contribution.weight,
        normalized_value_a=contribution.normalized_value_a,
        normalized_value_b=contribution.normalized_value_b,
        raw_contribution=contribution.raw_contribution,
        contribution_pct=contribution.contribution_pct,
    )


def _to_confidence_out(confidence: ConfidenceResult) -> ConfidenceOut:
    inputs = confidence.inputs
    return ConfidenceOut(
        confidence_engine_version=confidence.confidence_engine_version,
        confidence_config_version=confidence.confidence_config_version,
        value=confidence.value,
        raw=confidence.raw,
        calibrated_output=confidence.calibrated_output,
        credible_interval=None,
        inputs=ConfidenceInputsOut(
            evidence_sufficiency=inputs.evidence_sufficiency,
            n_bar=inputs.n_bar,
            coverage=inputs.coverage,
            ensemble_disagreement=inputs.ensemble_disagreement,
            ensemble_term_capped=inputs.ensemble_term_capped,
            historical_calibration=inputs.historical_calibration,
            calibrated=inputs.calibrated,
            calibration_n=inputs.calibration_n,
            extraction_entropy=inputs.extraction_entropy,
            extraction_path=inputs.extraction_path,
            margin_adequacy=inputs.margin_adequacy,
            margin=inputs.margin,
        ),
        weights_used=dict(confidence.weights_used),
    )


def _build_trace(simulation: Simulation, evidence: tuple[Evidence, ...]) -> TraceGraphOut:
    """``decision <- factor <- evidence`` - see ``api/schemas/simulation.py``'s module docstring."""
    decision_node_id = f"decision:{simulation.decision_id}"
    nodes = [TraceNodeOut(id=decision_node_id, kind="decision", label="decision")]
    edges: list[TraceEdgeOut] = []

    known_factor_ids = simulation.extraction.factors.known_ids()
    for factor_id in known_factor_ids:
        nodes.append(TraceNodeOut(id=f"factor:{factor_id}", kind="factor", label=str(factor_id)))

    for edge in evidence:
        evidence_node_id = f"evidence:{edge.id}"
        nodes.append(TraceNodeOut(id=evidence_node_id, kind="evidence", label=edge.polarity.value))
        edges.append(
            TraceEdgeOut(source=evidence_node_id, target=decision_node_id, kind="supports")
        )
        for factor_id in known_factor_ids:
            edges.append(
                TraceEdgeOut(source=f"factor:{factor_id}", target=evidence_node_id, kind="cites")
            )

    return TraceGraphOut(nodes=nodes, edges=edges)
