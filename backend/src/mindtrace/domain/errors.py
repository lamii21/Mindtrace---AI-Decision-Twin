"""Domain error hierarchy.

Schema and configuration problems must be explicit and actionable: they name the
file, the offending identifier or field, what was expected, and what was found.
The domain never silently repairs invalid model configuration (principle 15).
"""

from __future__ import annotations


class MindtraceError(Exception):
    """Base class for every error raised by MINDTRACE domain code."""


class DomainError(MindtraceError):
    """A domain rule was violated (as opposed to an infrastructure failure)."""


class SchemaError(DomainError):
    """Base class for problems loading or validating a canonical schema file."""

    def __init__(
        self, message: str, *, source: str | None = None, location: str | None = None
    ) -> None:
        """Build an actionable message: ``<source>[ at <location>]: <message>``."""
        self.source = source
        self.location = location
        prefix = source if source else "schema"
        loc = f" at {location}" if location else ""
        super().__init__(f"{prefix}{loc}: {message}")


class SchemaStructureError(SchemaError):
    """The file does not match its JSON Schema (shape, types, required fields)."""


class SchemaValidationError(SchemaError):
    """The file is structurally valid but violates a semantic rule.

    Examples: a duplicate factor id, anchors that are not strictly increasing,
    a ``range`` whose bounds are not on the declared scale.
    """


class SchemaConsistencyError(SchemaError):
    """Two schema files disagree.

    Examples: ``traits.yaml`` references a factor absent from ``factors.yaml``;
    ``interview.yaml``'s ``factor_schema_version`` does not match
    ``factors.yaml``'s ``version``.
    """
