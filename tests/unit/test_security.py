"""
tests/unit/test_security.py
────────────────────────────
Unit tests for JWT creation/verification and password hashing.
These tests are pure-Python — no DB, no HTTP.
"""

import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from jose import jwt

from app.core.exceptions import InvalidTokenError, TokenExpiredError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def user_id() -> uuid.UUID:
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture(scope="module")
def sample_access_token(user_id) -> str:
    return create_access_token(
        user_id=user_id,
        role="user",
        scopes=["read:own"],
    )


@pytest.fixture(scope="module")
def sample_refresh_token(user_id) -> str:
    return create_refresh_token(
        user_id=user_id,
        session_id="test-session-id",
    )


# ── Password hashing tests ────────────────────────────────────────────────────

class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        plain = "MySecret1!"
        hashed = hash_password(plain)
        assert hashed != plain

    def test_correct_password_verifies(self):
        plain = "MySecret1!"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_wrong_password_fails(self):
        hashed = hash_password("MySecret1!")
        assert verify_password("WrongPassword!", hashed) is False

    def test_empty_password_hashes_without_error(self):
        # Should not raise — let application layer enforce non-empty
        hashed = hash_password("")
        assert isinstance(hashed, str)

    def test_same_password_produces_different_hashes(self):
        """Argon2 uses a unique salt per hash."""
        plain = "MySecret1!"
        h1 = hash_password(plain)
        h2 = hash_password(plain)
        assert h1 != h2

    def test_very_long_password(self):
        long_pw = "Aa1!" * 32  # 128 chars
        hashed = hash_password(long_pw)
        assert verify_password(long_pw, hashed) is True


# ── Access token tests ────────────────────────────────────────────────────────

class TestAccessToken:
    def test_creates_valid_token(self, sample_access_token):
        assert isinstance(sample_access_token, str)
        assert len(sample_access_token) > 50

    def test_decodes_correct_claims(self, sample_access_token, user_id):
        payload = decode_access_token(sample_access_token)
        assert payload["sub"] == str(user_id)
        assert payload["role"] == "user"
        assert payload["scopes"] == ["read:own"]
        assert payload["type"] == "access"

    def test_contains_expiry(self, sample_access_token):
        payload = decode_access_token(sample_access_token)
        assert "exp" in payload
        assert "iat" in payload
        assert payload["exp"] > payload["iat"]

    def test_expired_token_raises(self, user_id):
        with patch("app.core.security._utcnow") as mock_now:
            # Issue token with backdated time so it's already expired
            mock_now.return_value = datetime.now(tz=timezone.utc) - timedelta(hours=2)
            expired = create_access_token(
                user_id=user_id, role="user", scopes=[]
            )
        with pytest.raises(TokenExpiredError):
            decode_access_token(expired)

    def test_refresh_token_rejected_as_access(self, sample_refresh_token):
        with pytest.raises(InvalidTokenError, match="Expected an access token"):
            decode_access_token(sample_refresh_token)

    def test_tampered_token_raises(self, sample_access_token):
        tampered = sample_access_token[:-5] + "XXXXX"
        with pytest.raises(InvalidTokenError):
            decode_access_token(tampered)

    def test_garbage_token_raises(self):
        with pytest.raises(InvalidTokenError):
            decode_access_token("not.a.jwt")


# ── Refresh token tests ───────────────────────────────────────────────────────

class TestRefreshToken:
    def test_creates_valid_token(self, sample_refresh_token):
        assert isinstance(sample_refresh_token, str)

    def test_decodes_correct_claims(self, sample_refresh_token, user_id):
        payload = decode_refresh_token(sample_refresh_token)
        assert payload["sub"] == str(user_id)
        assert payload["session_id"] == "test-session-id"
        assert payload["type"] == "refresh"

    def test_access_token_rejected_as_refresh(self, sample_access_token):
        with pytest.raises(InvalidTokenError, match="Expected a refresh token"):
            decode_refresh_token(sample_access_token)

    def test_expired_refresh_token_raises(self, user_id):
        with patch("app.core.security._utcnow") as mock_now:
            mock_now.return_value = datetime.now(tz=timezone.utc) - timedelta(days=2)
            expired = create_refresh_token(user_id=user_id, session_id="s1")
        with pytest.raises(TokenExpiredError):
            decode_refresh_token(expired)
