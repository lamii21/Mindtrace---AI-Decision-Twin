"""The I/O seam for loading canonical schema files.

Reads YAML/JSON from disk and runs JSON-Schema structural validation. It parses
nothing into domain objects and enforces no domain rules -- that is the job of
the pure ``parse_*`` functions in the sibling modules. Kept private (leading
underscore): callers use ``load_*`` in ``factors``/``traits``/``interview``.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JsonSchemaValidationError

from mindtrace.domain.errors import SchemaError, SchemaStructureError


def _to_json_compatible(value: Any) -> Any:
    """Recursively replace YAML-native, non-JSON types with their JSON form.

    JSON has no date type, but YAML's implicit resolver turns an unquoted
    ``2026-09-09`` scalar into a real ``datetime.date`` - regardless of whether
    the value started life as a string. Canonicalising to ISO strings right
    after parsing keeps every later step (JSON-Schema validation, ``parse_*``)
    working over plain JSON-compatible data, as the JSON Schemas assume.
    """
    if isinstance(value, datetime.date):  # datetime.datetime is a subclass of datetime.date
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _to_json_compatible(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_compatible(v) for v in value]
    return value


def read_yaml(path: Path) -> Any:
    """Parse a YAML file to plain, JSON-compatible Python data.

    Raises:
        SchemaError: if the file is missing or not valid YAML.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:  # missing / unreadable
        raise SchemaError("file could not be read", source=path.name) from exc
    try:
        return _to_json_compatible(yaml.safe_load(text))
    except yaml.YAMLError as exc:
        raise SchemaStructureError(f"invalid YAML ({exc})", source=path.name) from exc


def read_json(path: Path) -> Any:
    """Parse a JSON file to plain Python data."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SchemaError("file could not be read", source=path.name) from exc
    except json.JSONDecodeError as exc:
        raise SchemaStructureError(f"invalid JSON ({exc})", source=path.name) from exc


def validate_structure(data: Any, json_schema: Any, *, source: str) -> None:
    """Validate ``data`` against a JSON Schema, raising on the first problem.

    The error names the offending location as a slash-path so a bad field is
    trivial to find (principle: fail loudly and actionably).

    Raises:
        SchemaStructureError: if ``data`` does not conform.
    """
    validator = Draft202012Validator(json_schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if not errors:
        return
    first: JsonSchemaValidationError = errors[0]
    location = (
        "/" + "/".join(str(p) for p in first.absolute_path) if first.absolute_path else "<root>"
    )
    raise SchemaStructureError(first.message, source=source, location=location)
