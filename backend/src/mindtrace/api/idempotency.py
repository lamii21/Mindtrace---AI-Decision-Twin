"""Request-fingerprint helper for ``Idempotency-Key`` handling (``docs/api/08`` s1).

**Concurrency note (M6-API planning s9).** This implements "claim-after-
create": the router performs the create, then claims the resulting
``resource_id`` under the presented key. Sequential retries (a client resends
the same key after a timeout, never having seen the first response) are
handled correctly - the second call creates nothing new and replays the
first's resource. A genuinely *concurrent* duplicate (two requests with the
identical key in flight at the same instant) can each create a resource
before either claims; the loser's resource becomes a harmless orphan in the
event log, and both callers still observe the *same* resource id in their
response, so client-visible idempotency holds even though one extra
server-side event exists. Closing that residual window needs pre-claiming a
reserved id before creating, which is not implemented in M6 - documented as
a known limitation rather than silently accepted.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping


def fingerprint(payload: Mapping[str, object]) -> str:
    """A deterministic fingerprint of a request body - canonical JSON, SHA-256."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
