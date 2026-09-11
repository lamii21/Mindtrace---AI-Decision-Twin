"""Deterministic builders for minimal, valid schema dicts.

Tests mutate a deep copy of these to produce a single, targeted violation and
assert the loader/parser rejects it with the right error. Keeping the fixtures
self-contained (no disk I/O) keeps the parser-level tests fast and independent
of the real ``schema/*.yaml`` content.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from mindtrace.domain.paths import default_schema_dir

REAL_SCHEMA_DIR = default_schema_dir()


def _factor(
    factor_id: str,
    *,
    direction: str = "benefit",
    better: str = "higher",
    tier_extended: bool = False,
) -> dict[str, Any]:
    factor: dict[str, Any] = {
        "id": factor_id,
        "label": factor_id.title(),
        "description": f"Test factor {factor_id}.",
        "direction": direction,
        "range": ["very_low", "very_high"],
        "better": better,
        "can_be_inferred": True,
        "self_report_reliability": "medium",
    }
    if not tier_extended:
        factor["examples"] = [f"{factor_id} example"]
        factor["possible_evidence"] = ["some_evidence_tag"]
    return factor


def minimal_factors_dict() -> dict[str, Any]:
    """A valid two-core-factor, one-extended-factor taxonomy."""
    return {
        "version": 1,
        "released": "2026-09-09",
        "scale": {
            "levels": ["very_low", "low", "moderate", "high", "very_high"],
            "default_anchors": {
                "very_low": 0.0,
                "low": 0.25,
                "moderate": 0.5,
                "high": 0.75,
                "very_high": 1.0,
            },
        },
        "factors": [
            _factor("alpha", direction="benefit", better="higher"),
            _factor("beta", direction="cost", better="lower"),
        ],
        "extended_factors": [
            _factor("gamma", direction="benefit", better="higher", tier_extended=True),
        ],
    }


def minimal_traits_dict() -> dict[str, Any]:
    """A valid trait model covering ``alpha``, ``beta`` (core) and ``gamma`` (extended)."""
    return {
        "version": 1,
        "released": "2026-09-09",
        "factor_schema_version": 1,
        "importance_weights": {
            "prior_defaults": {"mu": 0.0, "sigma": 1.5},
            "posterior": "normal",
            "read_transform": "softmax_over_known",
            "credible_interval": 0.9,
            "traits": [
                {
                    "factor": "alpha",
                    "prior": {"mu": 0.0, "sigma": 1.4},
                    "self_report_reliability": "high",
                },
                {
                    "factor": "beta",
                    "prior": {"mu": 0.0, "sigma": 1.5},
                    "self_report_reliability": "medium",
                },
                {
                    "factor": "gamma",
                    "prior": {"mu": -0.6, "sigma": 0.6},
                    "self_report_reliability": "low",
                    "tier": "extended",
                },
            ],
        },
        "dispositions": {
            "posterior": "beta",
            "credible_interval": 0.9,
            "traits": [
                {
                    "id": "risk_tolerance",
                    "description": "Test disposition.",
                    "prior": {"alpha": 2.0, "beta": 2.0},
                    "kind": "latent",
                    "inferable_from": ["some_signal"],
                    "mechanical_effect": "Does something to the curve.",
                },
            ],
        },
        "report": {"low_confidence_threshold": 0.35, "min_evidence_for_inferred": 2},
    }


def minimal_interview_dict() -> dict[str, Any]:
    """A valid interview bank referencing ``alpha``/``beta`` and ``risk_tolerance``."""
    return {
        "version": 1,
        "released": "2026-09-09",
        "factor_schema_version": 1,
        "config": {
            "likert_warmup_factors": ["alpha"],
            "fixed_prefix_items": 1,
            "adaptive_suffix_max": 1,
            "target_total": [1, 2],
            "logistic_scale_s": 0.6,
            "pseudocount_kappa": 1.5,
            "consistency_check_item_ids": ["p01r"],
        },
        "pairwise": [
            {
                "id": "p01",
                "prompt_A": "Option A.",
                "prompt_B": "Option B.",
                "A": {"alpha": "h"},
                "B": {"alpha": "l"},
                "covers": ["alpha"],
            },
            {
                "id": "p01r",
                "prompt_A": "Option B.",
                "prompt_B": "Option A.",
                "A": {"alpha": "l"},
                "B": {"alpha": "h"},
                "covers": ["alpha"],
                "role": "consistency_check",
            },
        ],
        "disposition": [
            {
                "id": "d01",
                "target": "risk_tolerance",
                "type": "gamble",
                "prompt_A": "Safe.",
                "prompt_B": "Risky.",
                "risky_option": "B",
            },
        ],
    }


def deep_copy(data: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy a fixture dict so a test can mutate it without affecting others."""
    return copy.deepcopy(data)


def write_bundle(
    directory: Path,
    *,
    factors: dict[str, Any] | None = None,
    traits: dict[str, Any] | None = None,
    interview: dict[str, Any] | None = None,
) -> Path:
    """Write a (possibly broken) schema bundle to ``directory`` and return it.

    Copies the real JSON Schemas alongside so ``load_*`` can structurally
    validate against them. Any of the three data dicts may be omitted, in which
    case the minimal valid fixture is used.
    """
    directory.mkdir(parents=True, exist_ok=True)
    factors_data = factors if factors is not None else minimal_factors_dict()
    traits_data = traits if traits is not None else minimal_traits_dict()
    interview_data = interview if interview is not None else minimal_interview_dict()
    (directory / "factors.yaml").write_text(
        yaml.safe_dump(factors_data, sort_keys=False), encoding="utf-8"
    )
    (directory / "traits.yaml").write_text(
        yaml.safe_dump(traits_data, sort_keys=False), encoding="utf-8"
    )
    (directory / "interview.yaml").write_text(
        yaml.safe_dump(interview_data, sort_keys=False), encoding="utf-8"
    )
    for schema_file in ("factors.schema.json", "traits.schema.json", "interview.schema.json"):
        (directory / schema_file).write_text(
            (REAL_SCHEMA_DIR / schema_file).read_text(encoding="utf-8"), encoding="utf-8"
        )
    return directory
