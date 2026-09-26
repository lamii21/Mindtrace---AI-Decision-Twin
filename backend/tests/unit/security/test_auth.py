"""Tests for `mindtrace.security.auth` (M6-API)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from mindtrace.domain.ids import UserId
from mindtrace.security.auth import (
    TokenExpiredError,
    TokenMalformedError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

_SECRET = b"a" * 32
_OTHER_SECRET = b"b" * 32
_ALGORITHM = "HS256"
_NOW = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)


class TestPasswordHashing:
    def test_verify_accepts_the_correct_password(self) -> None:
        hashed = hash_password("correct horse battery staple")
        assert verify_password("correct horse battery staple", hashed) is True

    def test_verify_rejects_the_wrong_password(self) -> None:
        hashed = hash_password("correct horse battery staple")
        assert verify_password("wrong password entirely", hashed) is False

    def test_hash_is_argon2id(self) -> None:
        assert hash_password("x" * 12).startswith("$argon2id$")

    def test_hash_never_contains_the_plaintext(self) -> None:
        password = "a very specific plaintext password value"
        assert password not in hash_password(password)

    def test_hashing_the_same_password_twice_yields_different_hashes(self) -> None:
        assert hash_password("same password value!!") != hash_password("same password value!!")


class TestAccessToken:
    def test_round_trips_the_user_id(self) -> None:
        user_id = UserId(uuid4())
        token = create_access_token(
            user_id, secret=_SECRET, algorithm=_ALGORITHM, ttl_seconds=1800, now=_NOW
        )
        decoded = decode_access_token(token, secret=_SECRET, algorithm=_ALGORITHM, now=_NOW)
        assert decoded == user_id

    def test_expiry_is_checked_against_the_caller_supplied_now_not_the_wall_clock(self) -> None:
        """Invariant A: decode must not silently read the real clock (M6-API planning)."""
        user_id = UserId(uuid4())
        token = create_access_token(
            user_id, secret=_SECRET, algorithm=_ALGORITHM, ttl_seconds=1800, now=_NOW
        )
        just_before_expiry = _NOW + timedelta(seconds=1799)
        decoded = decode_access_token(
            token, secret=_SECRET, algorithm=_ALGORITHM, now=just_before_expiry
        )
        assert decoded == user_id

    def test_expired_token_fails_closed(self) -> None:
        user_id = UserId(uuid4())
        token = create_access_token(
            user_id, secret=_SECRET, algorithm=_ALGORITHM, ttl_seconds=1800, now=_NOW
        )
        after_expiry = _NOW + timedelta(seconds=1801)
        with pytest.raises(TokenExpiredError):
            decode_access_token(token, secret=_SECRET, algorithm=_ALGORITHM, now=after_expiry)

    def test_wrong_secret_fails_closed(self) -> None:
        user_id = UserId(uuid4())
        token = create_access_token(
            user_id, secret=_SECRET, algorithm=_ALGORITHM, ttl_seconds=1800, now=_NOW
        )
        with pytest.raises(TokenMalformedError):
            decode_access_token(token, secret=_OTHER_SECRET, algorithm=_ALGORITHM, now=_NOW)

    def test_malformed_token_fails_closed(self) -> None:
        with pytest.raises(TokenMalformedError):
            decode_access_token("not.a.jwt", secret=_SECRET, algorithm=_ALGORITHM, now=_NOW)

    def test_a_refresh_token_is_never_a_parseable_access_token(self) -> None:
        """The type boundary is structural, not a claim check (module docstring)."""
        refresh_token = generate_refresh_token()
        with pytest.raises(TokenMalformedError):
            decode_access_token(refresh_token, secret=_SECRET, algorithm=_ALGORITHM, now=_NOW)

    def test_a_token_missing_the_type_claim_is_rejected(self) -> None:
        bad_token = jwt.encode(
            {"sub": str(uuid4()), "iat": 0, "exp": 9999999999}, _SECRET, algorithm=_ALGORITHM
        )
        with pytest.raises(TokenMalformedError):
            decode_access_token(bad_token, secret=_SECRET, algorithm=_ALGORITHM, now=_NOW)

    def test_a_token_with_a_non_uuid_subject_is_rejected(self) -> None:
        bad_token = jwt.encode(
            {"sub": "not-a-uuid", "type": "access", "iat": 0, "exp": 9999999999},
            _SECRET,
            algorithm=_ALGORITHM,
        )
        with pytest.raises(TokenMalformedError):
            decode_access_token(bad_token, secret=_SECRET, algorithm=_ALGORITHM, now=_NOW)

    def test_a_token_missing_the_expiration_claim_is_rejected(self) -> None:
        bad_token = jwt.encode(
            {"sub": str(uuid4()), "type": "access", "iat": 0}, _SECRET, algorithm=_ALGORITHM
        )
        with pytest.raises(TokenMalformedError):
            decode_access_token(bad_token, secret=_SECRET, algorithm=_ALGORITHM, now=_NOW)


class TestRefreshToken:
    def test_generate_produces_high_entropy_distinct_tokens(self) -> None:
        assert generate_refresh_token() != generate_refresh_token()

    def test_hash_is_deterministic(self) -> None:
        token = generate_refresh_token()
        assert hash_refresh_token(token) == hash_refresh_token(token)

    def test_hash_never_contains_the_raw_token(self) -> None:
        token = generate_refresh_token()
        assert token not in hash_refresh_token(token)

    def test_different_tokens_hash_differently(self) -> None:
        assert hash_refresh_token(generate_refresh_token()) != hash_refresh_token(
            generate_refresh_token()
        )
