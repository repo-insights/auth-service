"""Unit tests for core security utilities."""

from __future__ import annotations

import time
import os

# Provide minimal env so config doesn't crash during import
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-minimum-32-chars!!")
os.environ.setdefault("S2S_SECRET_KEY", "test-s2s-secret")
os.environ.setdefault("D1_DATABASE_URL", "libsql://test.turso.io")
os.environ.setdefault("D1_AUTH_TOKEN", "test-token")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test.apps.googleusercontent.com")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-secret")
os.environ.setdefault("GOOGLE_REDIRECT_URI", "http://localhost:8000/callback")
os.environ.setdefault("SMTP_HOST", "smtp.test.com")
os.environ.setdefault("SMTP_USER", "user")
os.environ.setdefault("SMTP_PASSWORD", "pass")
os.environ.setdefault("EMAIL_FROM", "noreply@test.com")

import pytest
from jose import jwt as jose_jwt

from app.core.security import (
    create_access_token,
    create_email_verification_token,
    create_refresh_token,
    create_s2s_token,
    decode_access_token,
    hash_password,
    sha256_hex,
    verify_password,
)
from app.core.config import settings


# ─── Password hashing ────────────────────────────────────────────────────────

def test_hash_and_verify_password():
    plain = "SecurePass1!"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed)


def test_wrong_password_fails():
    assert not verify_password("WrongPass1!", hash_password("SecurePass1!"))


# ─── SHA-256 ─────────────────────────────────────────────────────────────────

def test_sha256_is_deterministic():
    assert sha256_hex("hello") == sha256_hex("hello")
    assert sha256_hex("hello") != sha256_hex("world")


# ─── Access token ────────────────────────────────────────────────────────────

def _make_token(**overrides):
    defaults = dict(
        user_id="user-123",
        email="alice@example.com",
        name="Alice",
        tenant_id="tenant-abc",
        team_id=None,
        role="user",
        plan="tier_1",
        customer_id=None,
        permissions=["read_repo"],
        token_version=1,
    )
    defaults.update(overrides)
    return create_access_token(**defaults)


def test_access_token_is_valid_jwt():
    token, payload = _make_token()
    decoded = decode_access_token(token)
    assert decoded["sub"] == "user-123"
    assert decoded["email"] == "alice@example.com"
    assert decoded["iss"] == settings.jwt_issuer
    assert decoded["aud"] == settings.jwt_audience


def test_access_token_contains_required_fields():
    token, payload = _make_token(permissions=["read_repo", "ask_ai"], token_version=3)
    decoded = decode_access_token(token)
    assert "jti" in decoded
    assert decoded["token_version"] == 3
    assert "ask_ai" in decoded["permissions"]


def test_access_token_expiry_is_in_future():
    token, _ = _make_token()
    decoded = decode_access_token(token)
    assert decoded["exp"] > time.time()


# ─── Refresh token ───────────────────────────────────────────────────────────

def test_refresh_token_is_opaque_and_hashable():
    raw, token_hash = create_refresh_token()
    assert len(raw) > 32
    assert sha256_hex(raw) == token_hash


def test_refresh_tokens_are_unique():
    raw1, _ = create_refresh_token()
    raw2, _ = create_refresh_token()
    assert raw1 != raw2


# ─── S2S token ───────────────────────────────────────────────────────────────

def test_s2s_token_contains_service_name():
    token, expires_in = create_s2s_token("repo-service")
    decoded = jose_jwt.decode(
        token,
        settings.s2s_secret_key,
        algorithms=[settings.jwt_algorithm],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )
    assert decoded["service_name"] == "repo-service"
    assert decoded["exp"] > time.time()
    assert expires_in == settings.s2s_token_expire_minutes * 60


# ─── Email verification token ────────────────────────────────────────────────

def test_email_verification_token():
    raw, token_hash = create_email_verification_token()
    assert len(raw) > 20
    assert sha256_hex(raw) == token_hash
