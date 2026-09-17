"""Section 19: run the confidence engine against *real* preference posterior data.

`effective_sample_sizes` (preference) and `evidence_sufficiency`'s `n_eff`
parameter (confidence, built in the previous milestone) turned out to be
exactly the same shape - `dict[FactorId, float]` - so this is a genuine
zero-change integration: nothing in `mindtrace.engines.confidence` is
modified to make this work. No weight/threshold in the confidence formula is
touched here either - only the *input* changes.
"""

from __future__ import annotations

from tests.support.mcda_fixtures import EXAMPLE_1_FACTORS, T_REF_WEIGHTS, TAXONOMY
from tests.support.preference_fixtures import TRAIT_MODEL, all_pairwise_observations

from mindtrace.domain.enums import ChoiceOption
from mindtrace.domain.ids import FactorId
from mindtrace.engines.confidence.compute import compute_confidence
from mindtrace.engines.confidence.config import DEFAULT_CONFIDENCE_CONFIG
from mindtrace.engines.mcda.decide import decide
from mindtrace.engines.preference.config import DEFAULT_PREFERENCE_CONFIG
from mindtrace.engines.preference.posterior import effective_sample_sizes, to_disposition_inputs
from mindtrace.engines.preference.prior import initial_posterior
from mindtrace.engines.preference.update import apply_pairwise_observations


def test_cold_start_preference_posterior_gives_the_same_zero_evidence_sufficiency() -> None:
    """No observations at all: `effective_sample_sizes` is 0 everywhere - matches the
    confidence engine's own cold-start default (`n_eff=None`) exactly."""
    posterior = initial_posterior(TRAIT_MODEL)
    n_eff = effective_sample_sizes(posterior.weights, TRAIT_MODEL)
    assert all(value == 0.0 for value in n_eff.values())

    dispositions = to_disposition_inputs(posterior.dispositions)
    decision = decide(TAXONOMY, T_REF_WEIGHTS, EXAMPLE_1_FACTORS, dispositions)
    without_preference = compute_confidence(decision, config=DEFAULT_CONFIDENCE_CONFIG)
    with_zero_n_eff = compute_confidence(decision, n_eff=n_eff, config=DEFAULT_CONFIDENCE_CONFIG)
    assert without_preference.value == with_zero_n_eff.value
    assert without_preference.inputs.evidence_sufficiency == 0.0


def test_a_fully_answered_interview_raises_evidence_sufficiency_above_cold_start() -> None:
    """After the full 24-item interview, real (nonzero) `n_eff` values flow straight
    into `evidence_sufficiency` and raise `C` above its cold-start floor - no
    change to the confidence engine's formula, weights, or interface at all."""
    prior = initial_posterior(TRAIT_MODEL)
    observations = all_pairwise_observations(ChoiceOption.A)
    posterior = apply_pairwise_observations(prior, observations, DEFAULT_PREFERENCE_CONFIG)
    n_eff = effective_sample_sizes(posterior.weights, TRAIT_MODEL)
    assert any(value > 0.0 for value in n_eff.values())

    dispositions = to_disposition_inputs(posterior.dispositions)
    decision = decide(TAXONOMY, T_REF_WEIGHTS, EXAMPLE_1_FACTORS, dispositions)

    cold_start = compute_confidence(decision, config=DEFAULT_CONFIDENCE_CONFIG)
    with_real_evidence = compute_confidence(decision, n_eff=n_eff, config=DEFAULT_CONFIDENCE_CONFIG)

    assert with_real_evidence.inputs.evidence_sufficiency > cold_start.inputs.evidence_sufficiency
    assert with_real_evidence.value > cold_start.value


def test_n_eff_keys_are_a_subset_of_confidence_engines_known_weights() -> None:
    """The bridge only ever needs to supply `n_eff` for factors the *decision* itself
    knows - extra entries in `n_eff` are harmless (evidence_sufficiency indexes by
    the decision's own known weights, per mindtrace.engines.confidence.evidence)."""
    posterior = initial_posterior(TRAIT_MODEL)
    n_eff = effective_sample_sizes(posterior.weights, TRAIT_MODEL)
    decision = decide(
        TAXONOMY, T_REF_WEIGHTS, EXAMPLE_1_FACTORS, to_disposition_inputs(posterior.dispositions)
    )
    known_ids = {FactorId(c.factor_id) for c in decision.contributions}
    assert known_ids.issubset(set(n_eff))
