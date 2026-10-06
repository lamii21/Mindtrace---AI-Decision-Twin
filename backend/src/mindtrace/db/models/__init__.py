"""Every ORM model, imported once so `Base.metadata` sees the full schema.

Alembic's ``env.py`` and ``create_all``-based test fixtures both rely on
importing this module before touching ``Base.metadata`` - a model class that
is never imported never registers itself.
"""

from __future__ import annotations

from mindtrace.db.models.audit_log import AuditLogModel
from mindtrace.db.models.consent_record import ConsentRecordModel
from mindtrace.db.models.decision import DecisionModel
from mindtrace.db.models.evidence import EvidenceModel
from mindtrace.db.models.idempotency_key import IdempotencyKeyModel
from mindtrace.db.models.interview_session import InterviewSessionModel
from mindtrace.db.models.memory import MemoryModel
from mindtrace.db.models.memory_event import MemoryEventModel
from mindtrace.db.models.prediction import PredictionModel
from mindtrace.db.models.refresh_token import RefreshTokenModel
from mindtrace.db.models.simulation import SimulationModel
from mindtrace.db.models.twin import TwinModel
from mindtrace.db.models.twin_version import TwinVersionModel
from mindtrace.db.models.user import UserModel
from mindtrace.db.models.user_data_key import UserDataKeyModel

__all__ = [
    "AuditLogModel",
    "ConsentRecordModel",
    "DecisionModel",
    "EvidenceModel",
    "IdempotencyKeyModel",
    "InterviewSessionModel",
    "MemoryEventModel",
    "MemoryModel",
    "PredictionModel",
    "RefreshTokenModel",
    "SimulationModel",
    "TwinModel",
    "TwinVersionModel",
    "UserDataKeyModel",
    "UserModel",
]
