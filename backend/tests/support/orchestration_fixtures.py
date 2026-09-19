"""Reusable fixtures for the M6-B orchestrator, composed from the fixtures
M3/M4/M5/M6-A already ship - never a parallel taxonomy/trait model of its own,
so a schema mismatch is never accidentally introduced by the test fixtures
themselves.
"""

from __future__ import annotations

import json

from mindtrace.domain.ids import FactorId
from mindtrace.domain.traits import PairwiseObservation, PreferencePosterior
from mindtrace.engines.preference.config import DEFAULT_PREFERENCE_CONFIG
from mindtrace.engines.preference.prior import initial_posterior
from mindtrace.engines.preference.update import apply_pairwise_observations
from mindtrace.llm.config import ExtractionConfig
from mindtrace.orchestration import SimulationConfig
from tests.support.llm_fixtures import SCENARIO
from tests.support.preference_fixtures import TAXONOMY, TRAIT_MODEL

__all__ = [
    "SCENARIO",
    "TAXONOMY",
    "TRAIT_MODEL",
    "cold_start_posterior",
    "default_config",
    "disagreeing_self_consistency_responses",
    "fully_known_response",
    "near_tie_response",
    "self_consistency_config",
    "sparse_response",
    "strong_evidence_posterior",
]

_FID_SKILL = FactorId("skill_growth")
_FID_FINANCIAL = FactorId("financial_return")

DEFAULT_EXTRACTION_CONFIG = ExtractionConfig(provider="fake", model="fake-orchestration-v1")


def default_config(*, self_consistency: bool = False) -> SimulationConfig:
    return SimulationConfig(
        extraction_config=DEFAULT_EXTRACTION_CONFIG, self_consistency=self_consistency
    )


def self_consistency_config() -> SimulationConfig:
    return default_config(self_consistency=True)


def cold_start_posterior() -> PreferencePosterior:
    return initial_posterior(TRAIT_MODEL)


def strong_evidence_posterior() -> PreferencePosterior:
    """A posterior with real evidence favouring `skill_growth` over `financial_return`.

    Built the same way M6-A's own `TestOneObservation`/`TestRepeatedObservations`
    fixtures are: real `PairwiseObservation`s run through the real
    `apply_pairwise_observations` engine call, never a hand-set `mu`/`sigma`.
    """
    prior = cold_start_posterior()
    obs = [
        PairwiseObservation(design={_FID_SKILL: 1.0, _FID_FINANCIAL: -1.0}, outcome=1.0, weight=1.0)
    ]
    return apply_pairwise_observations(prior, obs * 5, DEFAULT_PREFERENCE_CONFIG)


def _response_for(levels: dict[str, str]) -> str:
    """A schema/taxonomy-valid extraction JSON string covering exactly `levels`.

    `SCENARIO` itself is used as every known factor's `rationale_span` - it is
    trivially a literal substring of itself, so `validate_against_taxonomy`
    (M5) always accepts it regardless of which factors/levels a given test
    needs, without fabricating scenario-specific prose per factor.
    """
    factors = [
        {"factor_id": factor_id, "known": True, "level": level, "rationale_span": SCENARIO}
        for factor_id, level in levels.items()
    ]
    return json.dumps({"schema_version": "1", "factors": factors})


def fully_known_response() -> str:
    """Test H: every one of the 16 core factors reported `known=True`."""
    return _response_for(dict.fromkeys(TAXONOMY.core_ids, "moderate"))


def sparse_response() -> str:
    """Test I: only 2 of 16 core factors known - below M3's coverage gate."""
    return _response_for({"intrinsic_interest": "moderate", "downside_risk": "moderate"})


def disagreeing_self_consistency_responses() -> tuple[str, str]:
    """Test G: two internally-valid passes that disagree on `skill_growth`'s level.

    `very_high` vs `moderate` -> a two-step ordinal gap -> `agreement=0.0`
    (M5's own self-consistency scoring, spec/06 §4.4).
    """
    return (
        _response_for({"skill_growth": "very_high"}),
        _response_for({"skill_growth": "moderate"}),
    )


def near_tie_response() -> str:
    """Test J: alternating high/low across every core factor - full coverage, near-zero score."""
    levels = {
        str(factor_id): ("high" if index % 2 == 0 else "low")
        for index, factor_id in enumerate(TAXONOMY.core_ids)
    }
    return _response_for(levels)
