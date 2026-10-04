"""Persistence for M8's ``InterviewSession`` - thin, mutable operational state.

The answers themselves are never here: they are ``elicitation_answered``
events in the existing, already-encrypted ``memory_event`` table (see
``events/projectors/preference.py``). This table only tracks that a session
exists and whether/how it finished. No encrypted columns - ids and
timestamps only, never user-authored prose.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from mindtrace.db.models.interview_session import InterviewSessionModel
from mindtrace.db.session import user_scoped_session
from mindtrace.domain.ids import InterviewSessionId, TwinId, TwinVersionId, UserId
from mindtrace.domain.interview import InterviewSession


def create_session(user_id: UserId, *, now: datetime) -> InterviewSession:
    """Start a new interview session."""
    with user_scoped_session(user_id) as session:
        row = InterviewSessionModel(
            id=uuid4(),
            user_id=user_id,
            twin_id=None,
            started_at=now,
            completed_at=None,
            resulting_twin_version_id=None,
            interview_noise=None,
        )
        session.add(row)
        session.flush()
        return _to_domain(row)


def get_session(user_id: UserId, session_id: InterviewSessionId) -> InterviewSession | None:
    """One session, or ``None`` if it does not exist / is not visible (RLS)."""
    with user_scoped_session(user_id) as db_session:
        row = db_session.get(InterviewSessionModel, session_id)
        if row is None:
            return None
        return _to_domain(row)


def finalize_session(
    session: Session,
    *,
    session_id: InterviewSessionId,
    twin_id: TwinId,
    resulting_twin_version_id: TwinVersionId,
    interview_noise: float,
    now: datetime,
) -> None:
    """Mark a session finalized, within the caller-owned session (atomic with the Twin write).

    Raises:
        ValueError: ``session_id`` does not exist (the caller already holds
            a live reference - this should not occur in practice).
    """
    row = session.get(InterviewSessionModel, session_id)
    if row is None:  # pragma: no cover - caller already confirmed the session exists
        msg = f"interview session {session_id} not found"
        raise ValueError(msg)
    row.twin_id = twin_id
    row.completed_at = now
    row.resulting_twin_version_id = resulting_twin_version_id
    row.interview_noise = interview_noise


def _to_domain(row: InterviewSessionModel) -> InterviewSession:
    return InterviewSession(
        id=InterviewSessionId(row.id),
        user_id=UserId(row.user_id),
        twin_id=TwinId(row.twin_id) if row.twin_id is not None else None,
        started_at=row.started_at,
        completed_at=row.completed_at,
        resulting_twin_version_id=(
            TwinVersionId(row.resulting_twin_version_id)
            if row.resulting_twin_version_id is not None
            else None
        ),
        interview_noise=row.interview_noise,
    )
