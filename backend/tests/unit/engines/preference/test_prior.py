"""`initial_posterior`: the prior read as the zero-evidence posterior."""

from __future__ import annotations

from tests.support.preference_fixtures import TRAIT_MODEL

from mindtrace.domain.ids import DispositionId, FactorId
from mindtrace.engines.preference.config import ENGINE_VERSION
from mindtrace.engines.preference.prior import initial_posterior


def test_weight_posteriors_match_traits_yaml_exactly() -> None:
    posterior = initial_posterior(TRAIT_MODEL)
    for weight_spec in TRAIT_MODEL.weights:
        wp = posterior.weights[weight_spec.factor]
        assert wp.mu == weight_spec.prior.mu
        assert wp.sigma == weight_spec.prior.sigma


def test_disposition_posteriors_match_traits_yaml_exactly() -> None:
    posterior = initial_posterior(TRAIT_MODEL)
    for disposition_spec in TRAIT_MODEL.dispositions:
        dp = posterior.dispositions[disposition_spec.id]
        assert dp.alpha == disposition_spec.prior.alpha
        assert dp.beta == disposition_spec.prior.beta


def test_every_evidence_count_starts_at_zero() -> None:
    posterior = initial_posterior(TRAIT_MODEL)
    assert all(count == 0 for count in posterior.weight_evidence_count.values())
    assert all(count == 0 for count in posterior.disposition_evidence_count.values())


def test_covers_every_trait_in_the_model() -> None:
    posterior = initial_posterior(TRAIT_MODEL)
    assert set(posterior.weights) == TRAIT_MODEL.weight_factor_ids
    assert set(posterior.dispositions) == set(TRAIT_MODEL.disposition_ids)


def test_engine_version_defaults_to_the_module_constant() -> None:
    posterior = initial_posterior(TRAIT_MODEL)
    assert posterior.engine_version == ENGINE_VERSION


def test_trait_schema_version_matches_the_loaded_model() -> None:
    posterior = initial_posterior(TRAIT_MODEL)
    assert posterior.trait_schema_version == TRAIT_MODEL.version


def test_custom_engine_version_is_honoured() -> None:
    posterior = initial_posterior(TRAIT_MODEL, engine_version="99")
    assert posterior.engine_version == "99"


def test_skill_growth_and_risk_tolerance_are_present() -> None:
    posterior = initial_posterior(TRAIT_MODEL)
    assert FactorId("skill_growth") in posterior.weights
    assert DispositionId("risk_tolerance") in posterior.dispositions
