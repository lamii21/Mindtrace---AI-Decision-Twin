"""Every ORM model, imported once so `Base.metadata` sees the full schema.

Alembic's ``env.py`` and ``create_all``-based test fixtures both rely on
importing this module before touching ``Base.metadata`` - a model class that
is never imported never registers itself.
"""

from __future__ import annotations

from mindtrace.db.models.consent_record import ConsentRecordModel
from mindtrace.db.models.decision import DecisionModel
from mindtrace.db.models.memory import MemoryModel
from mindtrace.db.models.memory_event import MemoryEventModel
from mindtrace.db.models.user import UserModel
from mindtrace.db.models.user_data_key import UserDataKeyModel

__all__ = [
    "ConsentRecordModel",
    "DecisionModel",
    "MemoryEventModel",
    "MemoryModel",
    "UserDataKeyModel",
    "UserModel",
]
