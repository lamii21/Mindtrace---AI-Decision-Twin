"""`ensemble_disagreement` and the degenerate-twin guard (spec §06 §4.2)."""

from __future__ import annotations

import pytest

from mindtrace.domain.confidence import EnsembleObservation
from mindtrace.domain.enums import DecisionOutcome
from mindtrace.engines.confidence.config import DEFAULT_CONFIDENCE_CONFIG
from mindtrace.engines.confidence.ensemble import ensemble_term

_CONFIG = DEFAULT_CONFIDENCE_CONFIG
_ACCEPT = DecisionOutcome.ACCEPT
_REJECT = DecisionOutcome.REJECT


def test_no_ensemble_is_unavailable_not_favourable() -> None:
    term, disagreement, capped = ensemble_term(None, evidence_sufficiency_value=0.9, config=_CONFIG)
    assert term is None
    assert disagreement is None
    assert capped is False


def test_unanimous_tight_scores_give_low_disagreement_high_term() -> None:
    obs = EnsembleObservation(scores=(0.7, 0.71, 0.69, 0.70, 0.70), labels=(_ACCEPT,) * 5)
    term, disagreement, capped = ensemble_term(obs, evidence_sufficiency_value=0.9, config=_CONFIG)
    assert disagreement is not None
    assert disagreement < 0.05
    assert term == pytest.approx(1.0 - disagreement)
    assert capped is False


def test_disagreeing_labels_add_the_fixed_penalty() -> None:
    identical_scores = (0.5, 0.5)
    unanimous = ensemble_term(
        EnsembleObservation(scores=identical_scores, labels=(_ACCEPT, _ACCEPT)),
        evidence_sufficiency_value=0.9,
        config=_CONFIG,
    )
    split = ensemble_term(
        EnsembleObservation(scores=identical_scores, labels=(_ACCEPT, _REJECT)),
        evidence_sufficiency_value=0.9,
        config=_CONFIG,
    )
    assert unanimous[1] == pytest.approx(0.0)
    assert split[1] == pytest.approx(_CONFIG.label_disagree_penalty)


def test_wide_dispersion_saturates_disagreement_at_one() -> None:
    labels = (_ACCEPT, _REJECT, _ACCEPT, _REJECT)
    obs = EnsembleObservation(scores=(1.0, -1.0, 1.0, -1.0), labels=labels)
    term, disagreement, _ = ensemble_term(obs, evidence_sufficiency_value=0.9, config=_CONFIG)
    assert disagreement == pytest.approx(1.0)
    assert term == pytest.approx(0.0)


def test_degenerate_twin_guard_caps_the_term_when_evidence_is_thin() -> None:
    # Near-flat twins (tiny dispersion) look like perfect agreement, but with
    # evidence_sufficiency below the cutoff the guard must cap the term.
    obs = EnsembleObservation(scores=(0.01, 0.011, 0.009, 0.01), labels=(_ACCEPT,) * 4)
    term, _, capped = ensemble_term(obs, evidence_sufficiency_value=0.1, config=_CONFIG)
    assert capped is True
    assert term == _CONFIG.degenerate_ensemble_cap


def test_guard_does_not_fire_when_evidence_is_adequate() -> None:
    obs = EnsembleObservation(scores=(0.01, 0.011, 0.009, 0.01), labels=(_ACCEPT,) * 4)
    term, _, capped = ensemble_term(obs, evidence_sufficiency_value=0.9, config=_CONFIG)
    assert capped is False
    assert term is not None
    assert term > _CONFIG.degenerate_ensemble_cap
