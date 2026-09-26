"""Tests for `mindtrace.api.idempotency`."""

from __future__ import annotations

from mindtrace.api.idempotency import fingerprint


class TestFingerprint:
    def test_deterministic_for_the_same_payload(self) -> None:
        payload = {"kind": "note", "text": "x", "source": "declared"}
        assert fingerprint(payload) == fingerprint(payload)

    def test_key_order_does_not_change_the_fingerprint(self) -> None:
        assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})

    def test_different_payloads_fingerprint_differently(self) -> None:
        assert fingerprint({"text": "a"}) != fingerprint({"text": "b"})
