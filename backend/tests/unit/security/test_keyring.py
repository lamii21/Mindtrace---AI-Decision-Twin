"""Behavioral tests for `mindtrace.security.keyring` (ADR-009)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from mindtrace.domain.ids import UserId
from mindtrace.security.keyring import (
    DEK_LENGTH,
    MASTER_KEY_LENGTH,
    DekUnwrapError,
    EnvironmentKeyProvider,
    FakeKeyProvider,
    MasterKeyMalformedError,
    generate_dek,
)

_USER_A = UserId(uuid4())
_USER_B = UserId(uuid4())


class TestGenerateDek:
    def test_returns_the_expected_length(self) -> None:
        assert len(generate_dek()) == DEK_LENGTH

    def test_two_calls_never_collide(self) -> None:
        assert generate_dek() != generate_dek()


class TestMasterKeyValidation:
    def test_wrong_length_master_key_fails_closed_at_construction(self) -> None:
        with pytest.raises(MasterKeyMalformedError):
            EnvironmentKeyProvider(b"too-short")

    def test_correct_length_master_key_constructs_cleanly(self) -> None:
        EnvironmentKeyProvider(b"\x00" * MASTER_KEY_LENGTH)


class TestWrapUnwrapRoundTrip:
    def test_unwrap_recovers_the_exact_original_dek(self) -> None:
        provider = FakeKeyProvider()
        dek = generate_dek()
        wrapped, nonce = provider.wrap_dek(dek, user_id=_USER_A, key_version=1)
        assert provider.unwrap_dek(wrapped, nonce, user_id=_USER_A, key_version=1) == dek

    def test_wrapping_the_same_dek_twice_yields_different_bytes(self) -> None:
        provider = FakeKeyProvider()
        dek = generate_dek()
        first, _ = provider.wrap_dek(dek, user_id=_USER_A, key_version=1)
        second, _ = provider.wrap_dek(dek, user_id=_USER_A, key_version=1)
        assert first != second

    def test_wrapped_bytes_do_not_contain_the_raw_dek(self) -> None:
        provider = FakeKeyProvider()
        dek = generate_dek()
        wrapped, _nonce = provider.wrap_dek(dek, user_id=_USER_A, key_version=1)
        assert dek not in wrapped


class TestUnwrapFailsClosed:
    def test_wrong_user_fails_authentication(self) -> None:
        provider = FakeKeyProvider()
        wrapped, nonce = provider.wrap_dek(generate_dek(), user_id=_USER_A, key_version=1)
        with pytest.raises(DekUnwrapError):
            provider.unwrap_dek(wrapped, nonce, user_id=_USER_B, key_version=1)

    def test_wrong_key_version_fails_authentication(self) -> None:
        provider = FakeKeyProvider()
        wrapped, nonce = provider.wrap_dek(generate_dek(), user_id=_USER_A, key_version=1)
        with pytest.raises(DekUnwrapError):
            provider.unwrap_dek(wrapped, nonce, user_id=_USER_A, key_version=2)

    def test_different_master_keys_cannot_unwrap_each_others_output(self) -> None:
        provider_a = EnvironmentKeyProvider(b"\x01" * MASTER_KEY_LENGTH)
        provider_b = EnvironmentKeyProvider(b"\x02" * MASTER_KEY_LENGTH)
        wrapped, nonce = provider_a.wrap_dek(generate_dek(), user_id=_USER_A, key_version=1)
        with pytest.raises(DekUnwrapError):
            provider_b.unwrap_dek(wrapped, nonce, user_id=_USER_A, key_version=1)

    def test_tampered_wrapped_bytes_fail_authentication(self) -> None:
        provider = FakeKeyProvider()
        wrapped, nonce = provider.wrap_dek(generate_dek(), user_id=_USER_A, key_version=1)
        tampered = bytearray(wrapped)
        tampered[-1] ^= 0xFF
        with pytest.raises(DekUnwrapError):
            provider.unwrap_dek(bytes(tampered), nonce, user_id=_USER_A, key_version=1)


class TestFakeKeyProviderIsDeterministicAndNetworkFree:
    def test_two_instances_agree_byte_for_byte(self) -> None:
        dek = generate_dek()
        wrapped, nonce = FakeKeyProvider().wrap_dek(dek, user_id=_USER_A, key_version=1)
        # A brand-new instance, same fixed seed - no shared state, no env var.
        recovered = FakeKeyProvider().unwrap_dek(wrapped, nonce, user_id=_USER_A, key_version=1)
        assert recovered == dek
