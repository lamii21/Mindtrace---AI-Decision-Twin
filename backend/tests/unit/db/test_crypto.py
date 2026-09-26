"""Behavioral tests for `mindtrace.db.crypto` (ADR-009).

Library-guarantee + boundary tests, never a homemade statistical check on
the cipher itself (M6-Persistence/Foundation planning s13/s25): AES-GCM's
authentication property is `cryptography`'s to prove, not this suite's -
these tests prove *this module's* AAD binding, key-length validation, and
fail-closed behaviour around that primitive.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

from mindtrace.db.crypto import (
    DEK_LENGTH,
    AuthenticationError,
    MalformedKeyError,
    decrypt_field,
    encrypt_field,
)
from mindtrace.db.types import EnvelopeFormatError
from mindtrace.domain.ids import UserId

_DEK_A = b"\x11" * DEK_LENGTH
_DEK_B = b"\x22" * DEK_LENGTH
_USER_A = UserId(uuid4())
_USER_B = UserId(uuid4())
_ROW_1 = uuid4()
_ROW_2 = uuid4()


def _encrypt(
    plaintext: str = "hello",
    *,
    dek: bytes = _DEK_A,
    table: str = "memory_event",
    column: str = "payload",
    user_id: UserId = _USER_A,
    row_id: object = _ROW_1,
    key_version: int = 1,
) -> bytes:
    return encrypt_field(
        plaintext,
        dek=dek,
        table=table,
        column=column,
        user_id=user_id,
        row_id=row_id,  # type: ignore[arg-type]
        key_version=key_version,
    )


def _decrypt(
    envelope: bytes,
    *,
    dek: bytes = _DEK_A,
    table: str = "memory_event",
    column: str = "payload",
    user_id: UserId = _USER_A,
    row_id: object = _ROW_1,
) -> str:
    return decrypt_field(
        envelope,
        dek=dek,
        table=table,
        column=column,
        user_id=user_id,
        row_id=row_id,  # type: ignore[arg-type]
    )


class TestRoundTrip:
    def test_decrypt_recovers_the_exact_original_plaintext(self) -> None:
        envelope = _encrypt("a specific plaintext value: 12345")
        assert _decrypt(envelope) == "a specific plaintext value: 12345"

    def test_ciphertext_differs_from_the_plaintext(self) -> None:
        plaintext = "not-secret-looking plaintext"
        envelope = _encrypt(plaintext)
        assert plaintext.encode("utf-8") not in envelope


class TestNonDeterminism:
    def test_encrypting_the_same_plaintext_twice_yields_different_bytes(self) -> None:
        first = _encrypt("same plaintext")
        second = _encrypt("same plaintext")
        assert first != second
        # ... but both still decrypt to the same value.
        assert _decrypt(first) == _decrypt(second) == "same plaintext"


class TestWrongKeyRowColumnTableFailClosed:
    def test_wrong_dek_fails_authentication(self) -> None:
        envelope = _encrypt(dek=_DEK_A)
        with pytest.raises(AuthenticationError):
            _decrypt(envelope, dek=_DEK_B)

    def test_wrong_user_fails_authentication(self) -> None:
        envelope = _encrypt(user_id=_USER_A)
        with pytest.raises(AuthenticationError):
            _decrypt(envelope, user_id=_USER_B)

    def test_moving_ciphertext_to_another_row_fails_authentication(self) -> None:
        envelope = _encrypt(row_id=_ROW_1)
        with pytest.raises(AuthenticationError):
            _decrypt(envelope, row_id=_ROW_2)

    def test_moving_ciphertext_to_another_column_fails_authentication(self) -> None:
        envelope = _encrypt(column="payload")
        with pytest.raises(AuthenticationError):
            _decrypt(envelope, column="content")

    def test_moving_ciphertext_to_another_table_fails_authentication(self) -> None:
        envelope = _encrypt(table="memory_event")
        with pytest.raises(AuthenticationError):
            _decrypt(envelope, table="memory")


class TestTamperDetection:
    def test_tampered_ciphertext_fails_authentication(self) -> None:
        envelope = bytearray(_encrypt("tamper me"))
        envelope[-1] ^= 0xFF
        with pytest.raises(AuthenticationError):
            _decrypt(bytes(envelope))

    def test_tampered_nonce_fails_authentication(self) -> None:
        envelope = bytearray(_encrypt("tamper my nonce"))
        # Header layout: 1 byte format_version + 4 bytes key_version + 12 bytes nonce.
        envelope[5] ^= 0xFF
        with pytest.raises(AuthenticationError):
            _decrypt(bytes(envelope))

    def test_truncated_envelope_fails_with_a_format_error_not_a_crash(self) -> None:
        with pytest.raises(EnvelopeFormatError):
            _decrypt(b"\x00\x00")


class TestMalformedKey:
    def test_encrypt_with_wrong_length_dek_fails_closed(self) -> None:
        with pytest.raises(MalformedKeyError):
            _encrypt(dek=b"too-short")

    def test_decrypt_with_wrong_length_dek_fails_closed(self) -> None:
        envelope = _encrypt()
        with pytest.raises(MalformedKeyError):
            _decrypt(envelope, dek=b"too-short")

    def test_never_returns_a_placeholder_on_any_failure(self) -> None:
        """No code path in this module returns an empty string or a sentinel -
        every failure is an exception (M6-Persistence/Foundation planning s32)."""
        envelope = _encrypt()
        for bad_dek in (b"", os.urandom(16), os.urandom(64)):
            with pytest.raises(MalformedKeyError):
                _decrypt(envelope, dek=bad_dek)
