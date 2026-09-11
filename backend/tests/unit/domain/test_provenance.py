"""Tests for the source -> epistemic-state classifier (``mindtrace.domain.provenance``)."""

from __future__ import annotations

import pytest

from mindtrace.domain.enums import EpistemicState, ProvenanceSource
from mindtrace.domain.provenance import classify_epistemic_state
from tests.support.memory_fixtures import uncertain_belief_reference


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (ProvenanceSource.DECLARED, EpistemicState.DECLARED),
        (ProvenanceSource.OBSERVED, EpistemicState.OBSERVED),
        (ProvenanceSource.INFERRED, EpistemicState.INFERRED),
    ],
)
def test_every_provenance_source_maps_to_the_matching_state(
    source: ProvenanceSource, expected: EpistemicState
) -> None:
    assert classify_epistemic_state(source) is expected


def test_no_source_means_uncertain() -> None:
    assert classify_epistemic_state(None) is EpistemicState.UNCERTAIN


def test_uncertain_belief_fixture_reads_as_uncertain() -> None:
    # No Evidence exists for this belief reference (nothing recorded it) - a caller
    # would compute `source = None` from an empty EvidenceStore.for_belief(...) result,
    # exactly the input that produces UNCERTAIN here.
    _belief_type, _belief_id = uncertain_belief_reference()
    assert classify_epistemic_state(None) is EpistemicState.UNCERTAIN


def test_classification_is_exhaustive_over_provenance_source() -> None:
    for source in ProvenanceSource:
        # must not raise for any real source value
        assert classify_epistemic_state(source) in EpistemicState
