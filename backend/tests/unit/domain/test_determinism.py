"""Determinism tests (``docs/09-testing-strategy.md`` s2).

M1 has no domain *calculation* yet, but the schema parsers must already satisfy
the invariant every later engine depends on: same input -> same output, with no
hidden state, no wall-clock dependency, and no unseeded randomness.
"""

from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from typing import Any

from mindtrace.domain.factors import load_factor_taxonomy, parse_factor_taxonomy
from mindtrace.domain.interview import parse_interview_bank
from mindtrace.domain.paths import default_schema_dir
from mindtrace.domain.schema_bundle import SchemaBundle, load_schema_bundle
from mindtrace.domain.traits import parse_trait_model
from tests.support.schema_factories import (
    REAL_SCHEMA_DIR,
    minimal_factors_dict,
    minimal_interview_dict,
    minimal_traits_dict,
)


def test_parsing_the_same_factor_dict_twice_is_equal() -> None:
    data = minimal_factors_dict()
    first = parse_factor_taxonomy(copy.deepcopy(data))
    second = parse_factor_taxonomy(copy.deepcopy(data))
    assert first == second
    assert first.model_dump() == second.model_dump()


def test_parsing_the_same_trait_dict_twice_is_equal() -> None:
    taxonomy = parse_factor_taxonomy(minimal_factors_dict())
    data = minimal_traits_dict()
    first = parse_trait_model(copy.deepcopy(data), taxonomy)
    second = parse_trait_model(copy.deepcopy(data), taxonomy)
    assert first == second


def test_parsing_the_same_interview_dict_twice_is_equal() -> None:
    taxonomy = parse_factor_taxonomy(minimal_factors_dict())
    traits = parse_trait_model(minimal_traits_dict(), taxonomy)
    data = minimal_interview_dict()
    first = parse_interview_bank(copy.deepcopy(data), taxonomy=taxonomy, trait_model=traits)
    second = parse_interview_bank(copy.deepcopy(data), taxonomy=taxonomy, trait_model=traits)
    assert first == second


def test_loading_the_real_bundle_twice_from_disk_is_equal() -> None:
    first = load_schema_bundle(REAL_SCHEMA_DIR)
    second = load_schema_bundle(REAL_SCHEMA_DIR)
    assert first == second
    assert first.model_dump() == second.model_dump()


def test_real_bundle_dump_is_json_serialisable_and_stable(real_bundle: SchemaBundle) -> None:
    dumped_once = real_bundle.model_dump(mode="json")
    dumped_twice = real_bundle.model_dump(mode="json")
    assert json.dumps(dumped_once, sort_keys=True) == json.dumps(dumped_twice, sort_keys=True)


def test_taxonomy_parsing_does_not_depend_on_dict_key_order() -> None:
    data = minimal_factors_dict()
    reordered: dict[str, Any] = {
        "extended_factors": data.get("extended_factors", []),
        "factors": data["factors"],
        "scale": data["scale"],
        "released": data["released"],
        "version": data["version"],
    }
    assert parse_factor_taxonomy(data) == parse_factor_taxonomy(reordered)


def test_taxonomy_parsing_is_immune_to_poisoned_ambient_state(monkeypatch: Any) -> None:
    """Parsing must not consult the wall clock, the environment, or global RNG state."""

    def _boom_time() -> float:
        msg = "domain parsing must not read the wall clock"
        raise AssertionError(msg)

    monkeypatch.setattr("time.time", _boom_time)
    monkeypatch.setenv("SOME_UNRELATED_VAR", "poison")
    random.seed(1234567)  # arbitrary poisoned global RNG state

    data = minimal_factors_dict()
    first = parse_factor_taxonomy(copy.deepcopy(data))
    random.seed(7654321)
    second = parse_factor_taxonomy(copy.deepcopy(data))
    assert first == second


def test_load_factor_taxonomy_is_insensitive_to_cwd(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MINDTRACE_SCHEMA_DIR", raising=False)
    result = load_factor_taxonomy(REAL_SCHEMA_DIR)
    assert result.version == 1


def test_schema_dir_env_override_is_respected(tmp_path: Path, monkeypatch: Any) -> None:
    fake_dir = tmp_path / "schema"
    fake_dir.mkdir()
    monkeypatch.setenv("MINDTRACE_SCHEMA_DIR", str(fake_dir))
    assert default_schema_dir() == fake_dir.resolve()
