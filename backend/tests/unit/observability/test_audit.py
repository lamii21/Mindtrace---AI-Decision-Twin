"""Tests for building an ``AuditLog`` row (M9)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from uuid import UUID, uuid4

from mindtrace.domain.audit import AuditLog
from mindtrace.domain.ids import UserId
from mindtrace.observability.audit import build_audit_log

_FIXED_USER = UserId(uuid4())
_FIXED_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_FIXED_TARGET = uuid4()


def _build(
    *,
    payload: Mapping[str, object] | None = None,
    id_factory: Callable[[], UUID] | None = None,
) -> AuditLog:
    kwargs: dict[str, object] = {
        "user_id": _FIXED_USER,
        "actor": f"user:{_FIXED_USER}",
        "action": "belief.disputed",
        "target_type": "twin_version",
        "target_id": _FIXED_TARGET,
        "engine_version": "1",
        "payload": payload if payload is not None else {"item_id": "p01", "choice": "A"},
        "at": _FIXED_NOW,
    }
    if id_factory is not None:
        kwargs["id_factory"] = id_factory
    return build_audit_log(**kwargs)  # type: ignore[arg-type]


class TestBuildAuditLog:
    def test_builds_the_expected_fields(self) -> None:
        log = _build()
        assert log.user_id == _FIXED_USER
        assert log.actor == f"user:{_FIXED_USER}"
        assert log.action == "belief.disputed"
        assert log.target_type == "twin_version"
        assert log.target_id == _FIXED_TARGET
        assert log.engine_version == "1"
        assert log.at == _FIXED_NOW

    def test_payload_hash_is_deterministic_for_the_same_payload(self) -> None:
        first = _build()
        second = _build()
        assert first.payload_hash == second.payload_hash

    def test_payload_hash_differs_for_a_different_payload(self) -> None:
        first = _build(payload={"item_id": "p01", "choice": "A"})
        second = _build(payload={"item_id": "p01", "choice": "B"})
        assert first.payload_hash != second.payload_hash

    def test_payload_hash_is_insensitive_to_key_order(self) -> None:
        """Canonical JSON (``sort_keys=True``) - the hash must not depend on dict order."""
        first = _build(payload={"a": 1, "b": 2})
        second = _build(payload={"b": 2, "a": 1})
        assert first.payload_hash == second.payload_hash

    def test_never_includes_the_payload_itself_only_its_hash(self) -> None:
        """The whole point of AuditLog (docs/architecture/02): prove *what* produced a belief
        without storing the prose - a 64-hex-char sha256 digest, not the payload dict."""
        log = _build(payload={"reason": "I never actually said that"})
        assert "I never actually said that" not in log.payload_hash
        assert len(log.payload_hash) == 64
        int(log.payload_hash, 16)  # raises ValueError if not valid hex

    def test_id_factory_is_injectable_for_deterministic_tests(self) -> None:
        fixed_id = uuid4()
        log = _build(id_factory=lambda: fixed_id)
        assert UUID(str(log.id)) == fixed_id

    def test_default_id_factory_produces_a_fresh_id_each_call(self) -> None:
        first = _build()
        second = _build()
        assert first.id != second.id
