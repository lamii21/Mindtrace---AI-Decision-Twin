"""PostgreSQL persistence (M6-Persistence/Foundation).

Layer 1 of the architecture (``docs/architecture/01-repository-structure.md``):
depends only on ``domain``. Implements M2's ``EventStore`` port
(``mindtrace.events.store.EventStore``) and the field-level encryption
boundary ADR-009 defines - explicit ``encrypt_field``/``decrypt_field``
functions in ``db/crypto.py``, never a SQLAlchemy ``TypeDecorator`` (ADR-004
correction, ADR-009). Never imports ``mindtrace.security`` (mutually
isolated per ADR-009); a ``KeyProvider`` is passed in from outside.
"""

from __future__ import annotations
