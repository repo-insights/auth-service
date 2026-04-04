"""Shared test fixtures."""

from __future__ import annotations

import os
import pytest

# ── Environment bootstrap (must happen before any app import) ──────────────────
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-minimum-32-chars!!")
os.environ.setdefault("S2S_SECRET_KEY", "test-s2s-secret")
os.environ.setdefault("TURSO_DATABASE_URL", "libsql://test.turso.io")
os.environ.setdefault("TURSO_AUTH_TOKEN", "test-token")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test.apps.googleusercontent.com")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-secret")
os.environ.setdefault("GOOGLE_REDIRECT_URI", "http://localhost:8000/callback")
os.environ.setdefault("SMTP_HOST", "smtp.test.com")
os.environ.setdefault("SMTP_USER", "user")
os.environ.setdefault("SMTP_PASSWORD", "pass")
os.environ.setdefault("EMAIL_FROM", "noreply@test.com")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")


@pytest.fixture
def sample_user() -> dict:
    return {
        "id": "user-123",
        "email": "alice@example.com",
        "name": "Alice",
        "tenant_id": "tenant-abc",
        "role": "user",
        "token_version": 1,
        "is_active": 1,
        "is_email_verified": 1,
        "auth_provider": "email",
        "password_hash": None,
        "google_id": None,
        "avatar_url": None,
        "razorpay_customer_id": None,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "deleted_at": None,
    }


@pytest.fixture
def sample_tenant() -> dict:
    return {
        "id": "tenant-abc",
        "name": "Acme Corp",
        "slug": "acme-corp",
        "is_active": 1,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }
