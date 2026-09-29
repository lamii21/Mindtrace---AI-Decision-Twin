"""Decision CRUD + simulation (M6-API + M7).

**Status on create** (AG-5, ``docs/architecture/02-domain-model.md``): a
decision with both ``decided_at`` and ``chosen_option`` set is a
*retrospective* log of a past choice and is created directly ``committed``;
otherwise it starts ``draft``.

**Situation-freeze** (``docs/api/08`` s4: "situation fields immutable once
status >= simulated"): enforced here - ``DecisionPatch`` never carries
``title``/``category``/``context``/``options`` in the first place, so PATCH
has nothing to freeze; ``simulate()`` never writes them either (M6-Persistence
planning review confirms).

**Simulation** (M7): :func:`simulate` is the one call site in this codebase
outside ``orchestration``/tests that invokes ``orchestration.simulate()`` -
it computes nothing itself, only assembles inputs and persists the result.
No client PATCH can ever set ``status="simulated"`` directly
(:func:`_validate_transition`); only a completed, persisted simulation
causes that transition (``db.repositories.decision_repository.
mark_simulated``), and only forward, once, from ``draft``.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from mindtrace import orchestration
from mindtrace.db.crypto import KeyProvider
from mindtrace.db.repositories import (
    decision_repository,
    evidence_repository,
    simulation_repository,
)
from mindtrace.domain.confidence import ConfidenceResult
from mindtrace.domain.decision import DecisionResult
from mindtrace.domain.decision_record import Decision, DecisionOption
from mindtrace.domain.enums import (
    BeliefType,
    DecisionCategory,
    DecisionOutcome,
    DecisionStatus,
    EvidenceSourceKind,
    Polarity,
    UncertainReason,
)
from mindtrace.domain.evidence import Evidence
from mindtrace.domain.factors import FactorTaxonomy, load_factor_taxonomy
from mindtrace.domain.ids import DecisionId, EvidenceId, PredictionId, SimulationId, UserId
from mindtrace.domain.simulation import (
    ExtractionProvenance,
    Prediction,
    Simulation,
    SimulationExtraction,
    TwinConfigResult,
)
from mindtrace.domain.traits import TraitModel, load_trait_model
from mindtrace.engines.confidence.compute import confidence_uncertain_reason
from mindtrace.engines.confidence.config import ConfidenceConfig
from mindtrace.engines.preference.prior import initial_posterior
from mindtrace.llm.client import LLMClient
from mindtrace.llm.config import ExtractionConfig
from mindtrace.services.errors import (
    InvalidChosenOptionError,
    InvalidStatusTransitionError,
    ResourceNotFoundError,
)

_PATCH_REACHABLE_STATUSES = frozenset({DecisionStatus.COMMITTED, DecisionStatus.ARCHIVED})

# Loaded once, at import time - the same pattern ``tests/support/
# preference_fixtures.py`` already uses. Pure, deterministic, file-based; no
# I/O happens on any individual `simulate()` call because of this.
_TAXONOMY: FactorTaxonomy = load_factor_taxonomy()
_TRAIT_MODEL: TraitModel = load_trait_model(taxonomy=_TAXONOMY)

# `ExtractionConfig.provider`/`.model` have no default (M5's own decision -
# every caller must say which client it is actually using). "unavailable"/
# "none" name exactly what `api.deps.get_llm_client` injects by default
# today (`llm.providers.unavailable.UnavailableLLMClient`) - never a
# fabricated provider name like "anthropic" for a call that never reaches one.
_DEFAULT_EXTRACTION_CONFIG = ExtractionConfig(provider="unavailable", model="none")


def create(
    *,
    user_id: UserId,
    title: str,
    category: DecisionCategory,
    context: str,
    options: tuple[DecisionOption, ...],
    decided_at: datetime | None,
    chosen_option: str | None,
    key_provider: KeyProvider,
    now: datetime,
) -> Decision:
    """Create a new decision.

    Raises:
        InvalidChosenOptionError: ``chosen_option`` does not name one of
            ``options``.
    """
    if chosen_option is not None:
        _validate_chosen_option(chosen_option, options)
    status = (
        DecisionStatus.COMMITTED
        if decided_at is not None and chosen_option is not None
        else DecisionStatus.DRAFT
    )
    decision = Decision(
        id=DecisionId(uuid4()),
        user_id=user_id,
        title=title,
        category=category,
        context=context,
        options=options,
        chosen_option=chosen_option,
        reasoning=None,
        decided_at=decided_at,
        status=status,
        created_at=now,
    )
    decision_repository.create_decision(decision=decision, key_provider=key_provider)
    return decision


def get(user_id: UserId, decision_id: DecisionId, *, key_provider: KeyProvider) -> Decision:
    """Return one decision.

    Raises:
        ResourceNotFoundError: it does not exist, or is not owned by
            ``user_id`` (RLS makes the two indistinguishable - by design).
    """
    decision = decision_repository.get_decision(user_id, decision_id, key_provider=key_provider)
    if decision is None:
        msg = f"decision {decision_id} not found"
        raise ResourceNotFoundError(msg)
    return decision


def list_decisions(
    *,
    user_id: UserId,
    key_provider: KeyProvider,
    category: DecisionCategory | None = None,
    status: DecisionStatus | None = None,
) -> tuple[Decision, ...]:
    """Every decision for ``user_id`` matching the given filters."""
    return decision_repository.list_decisions(
        user_id, key_provider=key_provider, category=category, status=status
    )


def patch(
    *,
    user_id: UserId,
    decision_id: DecisionId,
    chosen_option: str | None,
    reasoning: str | None,
    status: DecisionStatus | None,
    key_provider: KeyProvider,
    now: datetime,
) -> Decision:
    """Apply a partial update to a decision's mutable fields.

    Raises:
        ResourceNotFoundError: as :func:`get`.
        InvalidChosenOptionError: ``chosen_option`` does not name one of the
            decision's own options.
        InvalidStatusTransitionError: ``status`` is not one M6 can honestly
            produce (``simulated`` needs M7), or is not reachable from the
            current status.

    Note: ``docs/api/08`` s4's situation-freeze rule ("immutable once status
    >= simulated") applies to ``title``/``category``/``context``/``options``
    - fields ``DecisionPatch`` never carries in the first place, so PATCH
    has nothing to freeze; ``run_simulation`` never writes them either.
    """
    current = get(user_id, decision_id, key_provider=key_provider)

    next_chosen_option = chosen_option if chosen_option is not None else current.chosen_option
    if next_chosen_option is not None:
        _validate_chosen_option(next_chosen_option, current.options)

    next_status = status if status is not None else current.status
    if status is not None and status != current.status:
        _validate_transition(current.status, status)

    next_reasoning = reasoning if reasoning is not None else current.reasoning
    becomes_committed = next_status is DecisionStatus.COMMITTED and current.decided_at is None
    next_decided_at = now if becomes_committed else current.decided_at

    updated = decision_repository.update_decision(
        user_id=user_id,
        decision_id=decision_id,
        chosen_option=next_chosen_option,
        reasoning=next_reasoning,
        status=next_status,
        decided_at=next_decided_at,
        key_provider=key_provider,
    )
    if updated is None:  # pragma: no cover - existence already confirmed by get() above
        msg = f"decision {decision_id} not found"
        raise ResourceNotFoundError(msg)
    return updated


def list_simulations(
    user_id: UserId, decision_id: DecisionId, *, key_provider: KeyProvider
) -> tuple[tuple[Simulation, Prediction], ...]:
    """Every simulation (+ its prediction) for one of the caller's own decisions, newest first.

    Raises:
        ResourceNotFoundError: as :func:`get`.
    """
    get(user_id, decision_id, key_provider=key_provider)  # ownership check; 404 if not owned
    return simulation_repository.list_simulations_for_decision(user_id, decision_id)


def get_simulation(user_id: UserId, simulation_id: SimulationId) -> tuple[Simulation, Prediction]:
    """Return one simulation and its prediction.

    Raises:
        ResourceNotFoundError: it does not exist, or is not owned by
            ``user_id`` (RLS makes the two indistinguishable - by design).
    """
    result = simulation_repository.get_simulation(user_id, simulation_id)
    if result is None:
        msg = f"simulation {simulation_id} not found"
        raise ResourceNotFoundError(msg)
    return result


def list_evidence_for_simulation(
    user_id: UserId, simulation_id: SimulationId
) -> tuple[Evidence, ...]:
    """Every ``decision_factor`` evidence edge :func:`simulate` wrote for ``simulation_id``."""
    return evidence_repository.list_for_belief(
        user_id, BeliefType.DECISION_FACTOR, UUID(str(simulation_id))
    )


def simulate(
    *,
    user_id: UserId,
    decision_id: DecisionId,
    llm_client: LLMClient,
    key_provider: KeyProvider,
    now: datetime,
    simulation_id: SimulationId | None = None,
) -> tuple[Simulation, Prediction]:
    """Validate, then run, one simulation against ``decision_id`` (M7).

    A convenience wrapper over :func:`validate_decision_for_simulation` +
    :func:`run_simulation` for callers that do not need them split apart
    (tests, and any non-idempotent caller). ``api/routers/simulate.py``
    calls the two separately - it must validate *before* claiming an
    ``Idempotency-Key``, so a bad ``decision_id`` fails immediately rather
    than burning a claim on a request that was never going to succeed
    (M7 planning s20).

    Raises:
        ResourceNotFoundError: as :func:`get`.
        InvalidStatusTransitionError: the decision is archived.
    """
    decision = validate_decision_for_simulation(user_id, decision_id, key_provider=key_provider)
    return run_simulation(decision, llm_client=llm_client, now=now, simulation_id=simulation_id)


def validate_decision_for_simulation(
    user_id: UserId, decision_id: DecisionId, *, key_provider: KeyProvider
) -> Decision:
    """Load and validate ``decision_id`` is simulatable - no side effects, no LLM call.

    Raises:
        ResourceNotFoundError: as :func:`get`.
        InvalidStatusTransitionError: the decision is archived - a closed
            decision is never simulated again.
    """
    decision = get(user_id, decision_id, key_provider=key_provider)
    if decision.status is DecisionStatus.ARCHIVED:
        msg = "an archived decision cannot be simulated"
        raise InvalidStatusTransitionError(msg)
    return decision


def run_simulation(
    decision: Decision,
    *,
    llm_client: LLMClient,
    now: datetime,
    simulation_id: SimulationId | None = None,
) -> tuple[Simulation, Prediction]:
    """Run and persist one simulation against an already-validated ``decision`` (M7).

    Calls ``orchestration.simulate()`` exactly once - the canonical M5 ->
    M6-A -> M3 -> M4 composition, computed nowhere else. The "base twin"
    posterior is a fresh cold-start prior (``engines.preference.prior.
    initial_posterior``) built from ``traits.yaml`` on every call: no
    ``Twin``/``TwinVersion`` persistence exists yet (M8), so there is
    nothing to load instead - see ``domain/simulation.py``'s module
    docstring.

    ``simulation_id`` lets a caller pre-allocate the id before this runs
    (the reserve-before-compute idempotency design in
    ``api/routers/simulate.py``); omitted, a fresh one is minted here.
    """
    user_id = decision.user_id
    decision_id = decision.id
    posterior = initial_posterior(_TRAIT_MODEL)
    config = orchestration.SimulationConfig(extraction_config=_DEFAULT_EXTRACTION_CONFIG)
    result = orchestration.simulate(
        decision.context, _TAXONOMY, _TRAIT_MODEL, posterior, llm_client, config=config
    )

    sim_id = simulation_id if simulation_id is not None else SimulationId(uuid4())
    prediction_id = PredictionId(uuid4())
    evidence_id = EvidenceId(uuid4())

    simulation = Simulation(
        id=sim_id,
        user_id=user_id,
        decision_id=decision_id,
        simulation_version=result.simulation_version,
        scenario_content_hash=result.scenario_content_hash,
        extraction=SimulationExtraction(
            status=result.extraction.status,
            factors=result.extraction.factors,
            metadata=ExtractionProvenance(**result.extraction.metadata.model_dump()),
            failure_type=result.extraction.failure_type,
            agreement=result.extraction.agreement,
        ),
        twin_configs=(
            TwinConfigResult(twin="base", preference=result.preference, decision=result.decision),
        ),
        model_confidence=result.confidence,
        created_at=now,
    )

    predicted_decision, uncertain_reason = _compose_final_label(
        result.decision, result.confidence, config.confidence_config
    )
    prediction = Prediction(
        id=prediction_id,
        decision_id=decision_id,
        simulation_id=sim_id,
        twin_version_id=None,
        predicted_decision=predicted_decision,
        uncertain_reason=uncertain_reason,
        predicted_confidence=result.confidence.value,
        credible_interval=None,
        factor_contributions=result.decision.contributions,
        margin=result.decision.margin,
        engine_version=result.simulation_version,
        created_at=now,
    )

    evidence = Evidence(
        id=evidence_id,
        user_id=user_id,
        belief_type=BeliefType.DECISION_FACTOR,
        belief_id=UUID(str(sim_id)),
        source_kind=EvidenceSourceKind.DECISION,
        source_id=UUID(str(decision_id)),
        weight=result.decision.coverage,
        polarity=Polarity.SUPPORT,
        engine_version=result.simulation_version,
        created_at=now,
    )

    simulation_repository.persist_simulation(
        simulation=simulation, prediction=prediction, evidence=evidence, user_id=user_id
    )
    return simulation, prediction


def _compose_final_label(
    decision: DecisionResult, confidence: ConfidenceResult, confidence_config: ConfidenceConfig
) -> tuple[DecisionOutcome, UncertainReason | None]:
    """The confidence-gated, product-level label (M7 planning s13).

    M3's own ``decision.label``/``uncertain_reason`` are never modified -
    this only decides what ``Prediction.predicted_decision`` reports, using
    ``UncertainReason``'s own documented priority order: the score-band/
    coverage gates (M3, already baked into ``decision.label`` before this
    runs) take precedence over the confidence gate, which only ever applies
    when M3 itself said ``ACCEPT``/``REJECT``.
    """
    if decision.label is DecisionOutcome.UNCERTAIN:
        return decision.label, decision.uncertain_reason
    reason = confidence_uncertain_reason(confidence, confidence_config)
    if reason is not None:
        return DecisionOutcome.UNCERTAIN, reason
    return decision.label, None


def _validate_chosen_option(chosen_option: str, options: tuple[DecisionOption, ...]) -> None:
    if chosen_option not in {option.id for option in options}:
        msg = f"chosen_option {chosen_option!r} does not name one of this decision's options"
        raise InvalidChosenOptionError(msg)


def _validate_transition(current: DecisionStatus, target: DecisionStatus) -> None:
    if target is DecisionStatus.SIMULATED:
        msg = "status cannot be set to 'simulated' directly - that requires M7's simulate engine"
        raise InvalidStatusTransitionError(msg)
    if target not in _PATCH_REACHABLE_STATUSES:
        msg = f"status {target} is not a valid PATCH target"
        raise InvalidStatusTransitionError(msg)
    if current is DecisionStatus.ARCHIVED:
        msg = "an archived decision's status cannot be changed"
        raise InvalidStatusTransitionError(msg)
