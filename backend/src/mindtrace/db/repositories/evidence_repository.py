"""``PostgresEvidenceStore`` - the Postgres adapter behind ``events.evidence_store.EvidenceStore``.

M2 defined the ``Evidence`` domain type and the ``EvidenceStore`` Protocol
with only ``InMemoryEvidenceStore`` (no belief-producing engine existed yet
to write real rows). This is the first real implementation, and it changes
nothing about the Protocol or the domain type - same shape as
``memory_repository``/``decision_repository``'s relationship to their domain
types.

Takes an already-open ``Session`` rather than opening its own (unlike every
other repository in this package): a simulation's ``Simulation`` +
``Prediction`` + ``Evidence`` rows must commit as one atomic unit (M7
planning s19), so the caller (``services/decision_service.py``) owns the one
``user_scoped_session`` and hands it to every write this call makes.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from mindtrace.db.models.evidence import EvidenceModel
from mindtrace.db.session import user_scoped_session
from mindtrace.domain.enums import BeliefType, EvidenceSourceKind, Polarity
from mindtrace.domain.evidence import Evidence
from mindtrace.domain.ids import EvidenceId, UserId


class PostgresEvidenceStore:
    """Implements :class:`~mindtrace.events.evidence_store.EvidenceStore` against Postgres."""

    def __init__(self, session: Session, *, user_id: UserId) -> None:
        """Wrap an already-open, already tenant-scoped ``session``."""
        self._session = session
        self._user_id = user_id

    def record(self, evidence: Evidence) -> Evidence:
        """Append ``evidence``. Never overwrites - the table carries no ``UPDATE`` grant."""
        self._session.add(
            EvidenceModel(
                id=evidence.id,
                user_id=evidence.user_id,
                belief_type=evidence.belief_type.value,
                belief_id=evidence.belief_id,
                source_kind=evidence.source_kind.value,
                source_id=evidence.source_id,
                weight=evidence.weight,
                polarity=evidence.polarity.value,
                engine_version=evidence.engine_version,
                created_at=evidence.created_at,
            )
        )
        return evidence

    def for_belief(self, belief_type: BeliefType, belief_id: UUID) -> tuple[Evidence, ...]:
        """See :meth:`~mindtrace.events.evidence_store.EvidenceStore.for_belief`."""
        rows = (
            self._session.execute(
                select(EvidenceModel).where(
                    EvidenceModel.user_id == self._user_id,
                    EvidenceModel.belief_type == belief_type.value,
                    EvidenceModel.belief_id == belief_id,
                )
            )
            .scalars()
            .all()
        )
        return tuple(_to_domain(row) for row in rows)

    def for_source(self, source_kind: EvidenceSourceKind, source_id: UUID) -> tuple[Evidence, ...]:
        """See :meth:`~mindtrace.events.evidence_store.EvidenceStore.for_source`."""
        rows = (
            self._session.execute(
                select(EvidenceModel).where(
                    EvidenceModel.user_id == self._user_id,
                    EvidenceModel.source_kind == source_kind.value,
                    EvidenceModel.source_id == source_id,
                )
            )
            .scalars()
            .all()
        )
        return tuple(_to_domain(row) for row in rows)


def list_for_belief(
    user_id: UserId, belief_type: BeliefType, belief_id: UUID
) -> tuple[Evidence, ...]:
    """A read-only, self-scoping variant of :meth:`PostgresEvidenceStore.for_belief`.

    For callers (the ``/v1/simulate`` response builder) that only need to
    *read* evidence already committed by a prior ``persist_simulation`` call,
    outside of that call's own atomic transaction.
    """
    with user_scoped_session(user_id) as session:
        return PostgresEvidenceStore(session, user_id=user_id).for_belief(belief_type, belief_id)


def _to_domain(row: EvidenceModel) -> Evidence:
    return Evidence(
        id=EvidenceId(row.id),
        user_id=UserId(row.user_id),
        belief_type=BeliefType(row.belief_type),
        belief_id=row.belief_id,
        source_kind=EvidenceSourceKind(row.source_kind),
        source_id=row.source_id,
        weight=row.weight,
        polarity=Polarity(row.polarity),
        engine_version=row.engine_version,
        created_at=row.created_at,
    )
