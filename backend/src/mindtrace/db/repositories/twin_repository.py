"""Persistence for AG-6's ``Twin``/``TwinVersion`` (M8).

Nothing here is encrypted (ADR-009): every ``TwinVersion`` field is numeric
posterior parameters / MCDA-ready weights, the same plaintext classification
M7 already established for ``Simulation``'s own JSONB columns.

:func:`get_or_create_twin`/:func:`allocate_next_version`/
:func:`create_twin_version` all take an already-open, caller-owned
``Session`` rather than opening their own (like ``simulation_repository.
persist_simulation``'s relationship to ``evidence_repository``): a
finalisation's ``Twin`` (if new) + ``TwinVersion`` + ``Evidence`` edges +
``interview_session`` update must commit as one atomic unit.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from mindtrace.db.models.twin import TwinModel
from mindtrace.db.models.twin_version import TwinVersionModel
from mindtrace.db.session import user_scoped_session
from mindtrace.domain.decision import DispositionInputs, WeightVector
from mindtrace.domain.enums import TwinVersionReason
from mindtrace.domain.ids import TwinId, TwinVersionId, UserId
from mindtrace.domain.traits import PreferencePosterior
from mindtrace.domain.twin import Twin, TwinVersion


def get_twin_for_user(user_id: UserId) -> Twin | None:
    """The user's twin, or ``None`` if they have not finalized an interview yet."""
    with user_scoped_session(user_id) as session:
        row = session.execute(
            select(TwinModel).where(TwinModel.user_id == user_id)
        ).scalar_one_or_none()
        if row is None:
            return None
        return _model_to_twin(row)


def get_latest_twin_version(user_id: UserId) -> TwinVersion | None:
    """The twin's highest-numbered (most recent) version, or ``None`` if none exists yet.

    This is the *only* place "latest" is ever resolved - a specific
    ``TwinVersion`` already referenced by a ``Prediction`` is looked up by
    id (:func:`get_twin_version`), never re-resolved to latest (M8 planning
    s12).
    """
    with user_scoped_session(user_id) as session:
        row = session.execute(
            select(TwinVersionModel)
            .where(TwinVersionModel.user_id == user_id)
            .order_by(TwinVersionModel.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            return None
        return _model_to_twin_version(row)


def get_twin_version(user_id: UserId, twin_version_id: TwinVersionId) -> TwinVersion | None:
    """One specific, immutable ``TwinVersion`` by id."""
    with user_scoped_session(user_id) as session:
        row = session.get(TwinVersionModel, twin_version_id)
        if row is None:
            return None
        return _model_to_twin_version(row)


def get_or_create_twin(session: Session, *, user_id: UserId, name: str, now: datetime) -> TwinModel:
    """Idempotent get-or-create, within a caller-owned session.

    One user has at most one twin in M8 (``UNIQUE(user_id)``, migration 0004).
    """
    row = session.execute(
        select(TwinModel).where(TwinModel.user_id == user_id)
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = TwinModel(id=uuid4(), user_id=user_id, name=name, created_at=now)
    session.add(row)
    session.flush()
    return row


def allocate_next_version(session: Session, twin: TwinModel) -> int:
    """Atomically allocate the next ``TwinVersion`` number (migration 0004's documented strategy).

    ``UPDATE twin SET next_twin_version = next_twin_version + 1 ...
    RETURNING next_twin_version - 1`` takes a row lock on this twin's row
    for the transaction's duration - two concurrent finalisations for the
    *same* twin serialise on that lock and can never allocate the same
    number; finalisations for different twins lock different rows and
    proceed fully in parallel (identical in spirit to ``users.
    next_event_seq``'s allocation in ``db/event_store.py``).
    """
    allocated: int = (
        session.execute(
            update(TwinModel)
            .where(TwinModel.id == twin.id)
            .values(next_twin_version=TwinModel.next_twin_version + 1)
            .returning(TwinModel.next_twin_version)
        ).scalar_one()
        - 1
    )
    return allocated


def create_twin_version(session: Session, *, twin_version: TwinVersion) -> None:
    """Insert one immutable ``TwinVersion`` row, within the caller-owned session."""
    session.add(_twin_version_to_model(twin_version))


def _model_to_twin(row: TwinModel) -> Twin:
    return Twin(
        id=TwinId(row.id),
        user_id=UserId(row.user_id),
        name=row.name,
        created_at=row.created_at,
    )


def _twin_version_to_model(twin_version: TwinVersion) -> TwinVersionModel:
    return TwinVersionModel(
        id=twin_version.id,
        user_id=twin_version.user_id,
        twin_id=twin_version.twin_id,
        version=twin_version.version,
        trait_snapshot=twin_version.trait_snapshot.model_dump(mode="json"),
        weights=twin_version.weights.model_dump(mode="json"),
        dispositions=twin_version.dispositions.model_dump(mode="json"),
        reason=twin_version.reason.value,
        engine_version=twin_version.engine_version,
        projection_version=twin_version.projection_version,
        factor_schema_version=twin_version.factor_schema_version,
        trait_schema_version=twin_version.trait_schema_version,
        created_at=twin_version.created_at,
    )


def _model_to_twin_version(row: TwinVersionModel) -> TwinVersion:
    return TwinVersion(
        id=TwinVersionId(row.id),
        user_id=UserId(row.user_id),
        twin_id=TwinId(row.twin_id),
        version=row.version,
        trait_snapshot=PreferencePosterior.model_validate(row.trait_snapshot),
        weights=WeightVector.model_validate(row.weights),
        dispositions=DispositionInputs.model_validate(row.dispositions),
        reason=TwinVersionReason(row.reason),
        engine_version=row.engine_version,
        projection_version=row.projection_version,
        factor_schema_version=row.factor_schema_version,
        trait_schema_version=row.trait_schema_version,
        created_at=row.created_at,
    )
