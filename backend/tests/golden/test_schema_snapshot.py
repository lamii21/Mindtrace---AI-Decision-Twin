"""Golden test: the parsed schema bundle is a frozen, reviewable snapshot.

A diff here means the taxonomy, trait model, or interview bank actually changed
shape or values - which must be a deliberate, reviewed edit (``docs/spec/03``
s5: a structural schema change is a major version bump). To update the
snapshot after a deliberate change, run once with ``MINDTRACE_GOLDEN_UPDATE=1``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from mindtrace.domain.schema_bundle import SchemaBundle

GOLDEN_PATH = Path(__file__).parent / "data" / "schema_snapshot.json"


def _canonical(bundle: SchemaBundle) -> str:
    return json.dumps(bundle.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def test_schema_bundle_matches_golden_snapshot(real_bundle: SchemaBundle) -> None:
    actual = _canonical(real_bundle)

    if os.environ.get("MINDTRACE_GOLDEN_UPDATE") == "1":
        GOLDEN_PATH.write_text(actual, encoding="utf-8")
        return

    assert GOLDEN_PATH.exists(), (
        f"{GOLDEN_PATH} is missing - generate it once with MINDTRACE_GOLDEN_UPDATE=1"
    )
    expected = GOLDEN_PATH.read_text(encoding="utf-8")
    assert actual == expected, (
        "the parsed schema bundle no longer matches tests/golden/data/schema_snapshot.json. "
        "If this change to schema/*.yaml was deliberate, regenerate with "
        "MINDTRACE_GOLDEN_UPDATE=1 pytest tests/golden/test_schema_snapshot.py and review the diff."
    )
