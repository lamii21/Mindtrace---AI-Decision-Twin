"""The encrypted envelope's physical byte layout (ADR-009).

A pure struct pack/unpack, no SQLAlchemy, no cryptography - deliberately the
smallest possible module so the on-disk shape of a ciphertext column is
independently readable and testable apart from the AEAD logic that produces
it (``db/crypto.py``).

::

    format_version : 1 byte,  unsigned            (starts at 1)
    key_version     : 4 bytes, unsigned big-endian (which user DEK encrypted this)
    nonce           : 12 bytes                     (unique per encryption call)
    ciphertext      : remaining bytes               (AESGCM output; tag appended)
"""

from __future__ import annotations

import struct

from mindtrace.domain.errors import DomainError

ENVELOPE_FORMAT_VERSION = 1
NONCE_LENGTH = 12

_HEADER = struct.Struct(">BI12s")


class EnvelopeFormatError(DomainError):
    """The stored bytes are not a well-formed encrypted envelope."""


def pack_envelope(*, key_version: int, nonce: bytes, ciphertext: bytes) -> bytes:
    """Serialise one encrypted value into its stored ``BYTEA`` representation.

    Raises:
        EnvelopeFormatError: ``nonce`` is not exactly :data:`NONCE_LENGTH`
            bytes, or ``key_version`` does not fit an unsigned 32-bit field.
    """
    if len(nonce) != NONCE_LENGTH:
        msg = f"nonce must be exactly {NONCE_LENGTH} bytes, got {len(nonce)}"
        raise EnvelopeFormatError(msg)
    try:
        header = _HEADER.pack(ENVELOPE_FORMAT_VERSION, key_version, nonce)
    except struct.error as exc:
        msg = f"key_version {key_version!r} does not fit an unsigned 32-bit field"
        raise EnvelopeFormatError(msg) from exc
    return header + ciphertext


def unpack_envelope(data: bytes) -> tuple[int, int, bytes, bytes]:
    """Return ``(format_version, key_version, nonce, ciphertext)``.

    Raises:
        EnvelopeFormatError: ``data`` is shorter than one header.
    """
    if len(data) < _HEADER.size:
        msg = f"envelope too short: {len(data)} bytes, expected at least {_HEADER.size}"
        raise EnvelopeFormatError(msg)
    format_version, key_version, nonce = _HEADER.unpack(data[: _HEADER.size])
    ciphertext = data[_HEADER.size :]
    return format_version, key_version, nonce, ciphertext
