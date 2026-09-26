"""The only code (besides ``db/event_store.py``) that writes SQL / calls ``db.crypto``.

Deliberately minimal for this milestone: insert/get/list, no business rules
(ownership checks, status transitions, ``Idempotency-Key`` handling belong to
``services/``, which does not exist yet - M6-Persistence/Foundation planning
s2). Each function opens and commits its own ``db.session.user_scoped_session``
- there is no ``services/`` layer yet to own a transaction spanning several
repository calls, so each function is its own transaction, the same pattern
``db/event_store.py`` already uses.
"""

from __future__ import annotations
