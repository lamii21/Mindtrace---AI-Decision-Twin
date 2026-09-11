"""Load and cross-validate the three canonical schema files as one unit.

The individual parsers already check each file against the others where the
dependency is local (traits -> factors, interview -> factors + traits) *as long
as they are loaded against the same* :class:`FactorTaxonomy` *instance* - which
:func:`load_schema_bundle` guarantees by construction. :class:`SchemaBundle`
additionally enforces the whole-bundle version agreement as a real, always-on
model invariant (not just a loader-time convenience), so constructing a bundle
directly from independently-loaded pieces is just as safe.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, model_validator

from mindtrace.domain.errors import SchemaConsistencyError
from mindtrace.domain.factors import FactorTaxonomy, load_factor_taxonomy
from mindtrace.domain.interview import InterviewBank, load_interview_bank
from mindtrace.domain.paths import default_schema_dir
from mindtrace.domain.traits import TraitModel, load_trait_model


class SchemaBundle(BaseModel):
    """The three canonical schemas, parsed and mutually consistent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    factors: FactorTaxonomy
    traits: TraitModel
    interview: InterviewBank

    @model_validator(mode="after")
    def _versions_agree(self) -> SchemaBundle:
        versions = {
            "factors.yaml": self.factors.version,
            "traits.yaml": self.traits.factor_schema_version,
            "interview.yaml": self.interview.factor_schema_version,
        }
        if len(set(versions.values())) != 1:
            raise SchemaConsistencyError(
                f"factor schema versions disagree across the bundle: {versions}",
                source="schema bundle",
            )
        return self

    @property
    def schema_version(self) -> int:
        """The common factor-schema version the whole bundle is pinned to."""
        return self.factors.version


def load_schema_bundle(schema_dir: Path | None = None) -> SchemaBundle:
    """Load ``factors.yaml``, ``traits.yaml`` and ``interview.yaml`` and cross-validate them.

    Raises:
        SchemaError: (or a subclass) naming the file and location of the first
            problem found.
    """
    directory = schema_dir or default_schema_dir()
    factors = load_factor_taxonomy(directory)
    traits = load_trait_model(directory, taxonomy=factors)
    interview = load_interview_bank(directory, taxonomy=factors, trait_model=traits)
    return SchemaBundle(factors=factors, traits=traits, interview=interview)
