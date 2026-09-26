"""Tests for the encrypted envelope's byte layout (`mindtrace.db.types`)."""

from __future__ import annotations

import pytest

from mindtrace.db.types import (
    ENVELOPE_FORMAT_VERSION,
    NONCE_LENGTH,
    EnvelopeFormatError,
    pack_envelope,
    unpack_envelope,
)


class TestRoundTrip:
    def test_pack_then_unpack_recovers_every_field(self) -> None:
        nonce = b"\x01" * NONCE_LENGTH
        ciphertext = b"ciphertext-and-tag-bytes"
        envelope = pack_envelope(key_version=7, nonce=nonce, ciphertext=ciphertext)
        fmt, key_version, out_nonce, out_ciphertext = unpack_envelope(envelope)
        assert fmt == ENVELOPE_FORMAT_VERSION
        assert key_version == 7
        assert out_nonce == nonce
        assert out_ciphertext == ciphertext

    def test_empty_ciphertext_round_trips(self) -> None:
        envelope = pack_envelope(key_version=1, nonce=b"\x00" * NONCE_LENGTH, ciphertext=b"")
        *_rest, ciphertext = unpack_envelope(envelope)
        assert ciphertext == b""


class TestMalformedInput:
    def test_wrong_nonce_length_fails_closed(self) -> None:
        with pytest.raises(EnvelopeFormatError, match="nonce"):
            pack_envelope(key_version=1, nonce=b"\x00" * (NONCE_LENGTH - 1), ciphertext=b"x")

    def test_key_version_out_of_range_fails_closed(self) -> None:
        with pytest.raises(EnvelopeFormatError, match="key_version"):
            pack_envelope(key_version=2**33, nonce=b"\x00" * NONCE_LENGTH, ciphertext=b"x")

    def test_truncated_envelope_fails_closed(self) -> None:
        with pytest.raises(EnvelopeFormatError, match="too short"):
            unpack_envelope(b"\x01\x02")
