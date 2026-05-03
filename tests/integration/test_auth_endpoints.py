"""
tests/integration/test_auth_endpoints.py
──────────────────────────────────────────
Integration tests for /v1/auth/* endpoints.
Uses an in-memory SQLite DB and a mocked Redis to avoid external dependencies.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.security import create_access_token, create_refresh_token
from app.models.user import User


# ── /auth/signup ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestSignup:
    async def test_signup_success(self, client: AsyncClient):
        response = await client.post(
            "/v1/auth/signup",
            json={"email": "newuser@example.com", "password": "StrongPass1!"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["user"]["email"] == "newuser@example.com"
        assert data["user"]["role"] == "user"
        assert "message" in data

    async def test_signup_duplicate_email(self, client: AsyncClient, sample_user: User):
        response = await client.post(
            "/v1/auth/signup",
            json={"email": sample_user.email, "password": "StrongPass1!"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "EMAIL_EXISTS"

    async def test_signup_weak_password_rejected(self, client: AsyncClient):
        response = await client.post(
            "/v1/auth/signup",
            json={"email": "weak@example.com", "password": "password"},
        )
        assert response.status_code == 422

    async def test_signup_invalid_email_rejected(self, client: AsyncClient):
        response = await client.post(
            "/v1/auth/signup",
            json={"email": "not-an-email", "password": "StrongPass1!"},
        )
        assert response.status_code == 422

    async def test_signup_missing_fields(self, client: AsyncClient):
        response = await client.post("/v1/auth/signup", json={})
        assert response.status_code == 422


# ── /auth/login ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestLogin:
    async def test_login_success(self, client: AsyncClient, sample_user: User):
        response = await client.post(
            "/v1/auth/login",
            json={"email": sample_user.email, "password": "SecurePass1!"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "Bearer"
        assert data["expires_in"] == 30 * 60

    async def test_login_wrong_password(self, client: AsyncClient, sample_user: User):
        response = await client.post(
            "/v1/auth/login",
            json={"email": sample_user.email, "password": "WrongPass1!"},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"

    async def test_login_nonexistent_email(self, client: AsyncClient):
        response = await client.post(
            "/v1/auth/login",
            json={"email": "ghost@example.com", "password": "SomePass1!"},
        )
        assert response.status_code == 401

    async def test_login_locked_account(self, client: AsyncClient, locked_user: User):
        response = await client.post(
            "/v1/auth/login",
            json={"email": locked_user.email, "password": "SecurePass1!"},
        )
        assert response.status_code == 423
        assert response.json()["error"]["code"] == "ACCOUNT_LOCKED"

    async def test_login_missing_email(self, client: AsyncClient):
        response = await client.post(
            "/v1/auth/login", json={"password": "StrongPass1!"}
        )
        assert response.status_code == 422


# ── /auth/refresh ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestRefreshTokens:
    async def test_refresh_success(self, client: AsyncClient, sample_user: User):
        # First login to get a real refresh token stored in DB
        login_resp = await client.post(
            "/v1/auth/login",
            json={"email": sample_user.email, "password": "SecurePass1!"},
        )
        assert login_resp.status_code == 200
        refresh_token = login_resp.json()["refresh_token"]

        # Use it to get a new token pair
        refresh_resp = await client.post(
            "/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_resp.status_code == 200
        data = refresh_resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        # Rotation: new refresh token must differ from the old one
        assert data["refresh_token"] != refresh_token

    async def test_refresh_with_invalid_token(self, client: AsyncClient):
        response = await client.post(
            "/v1/auth/refresh",
            json={"refresh_token": "definitely.not.valid"},
        )
        assert response.status_code == 401

    async def test_refresh_reuse_revokes_all_sessions(
        self, client: AsyncClient, sample_user: User
    ):
        # Login to get tokens
        login_resp = await client.post(
            "/v1/auth/login",
            json={"email": sample_user.email, "password": "SecurePass1!"},
        )
        original_token = login_resp.json()["refresh_token"]

        # Use token once (this rotates it)
        await client.post(
            "/v1/auth/refresh",
            json={"refresh_token": original_token},
        )

        # Attempt to reuse the original (now revoked) token
        reuse_resp = await client.post(
            "/v1/auth/refresh",
            json={"refresh_token": original_token},
        )
        # Should fail — reuse detection kicks in
        assert reuse_resp.status_code == 401


# ── /auth/logout ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestLogout:
    async def test_logout_success(self, client: AsyncClient, sample_user: User):
        login_resp = await client.post(
            "/v1/auth/login",
            json={"email": sample_user.email, "password": "SecurePass1!"},
        )
        refresh_token = login_resp.json()["refresh_token"]

        logout_resp = await client.post(
            "/v1/auth/logout",
            json={"refresh_token": refresh_token},
        )
        assert logout_resp.status_code == 200
        assert "Logged out" in logout_resp.json()["message"]

    async def test_logout_unknown_token_is_idempotent(self, client: AsyncClient):
        """Logout with an unknown token should not error — just no-op."""
        # Build a syntactically valid JWT that isn't in the DB
        fake_token = create_refresh_token(
            user_id=uuid.uuid4(), session_id="ghost-session"
        )
        response = await client.post(
            "/v1/auth/logout",
            json={"refresh_token": fake_token},
        )
        assert response.status_code == 200


# ── /users/me ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestGetMe:
    async def _get_access_token(self, client: AsyncClient, user: User) -> str:
        resp = await client.post(
            "/v1/auth/login",
            json={"email": user.email, "password": "SecurePass1!"},
        )
        return resp.json()["access_token"]

    async def test_get_me_authenticated(self, client: AsyncClient, sample_user: User):
        token = await self._get_access_token(client, sample_user)
        resp = await client.get(
            "/v1/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == sample_user.email
        assert data["role"] == "user"
        assert "hashed_password" not in data  # Never leak hashes

    async def test_get_me_no_token(self, client: AsyncClient):
        resp = await client.get("/v1/users/me")
        assert resp.status_code == 401

    async def test_get_me_invalid_token(self, client: AsyncClient):
        resp = await client.get(
            "/v1/users/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401

    async def test_get_me_expired_token(self, client: AsyncClient, sample_user: User):
        from datetime import timedelta, timezone
        from unittest.mock import patch as _patch

        with _patch("app.core.security._utcnow") as mock_now:
            mock_now.return_value = (
                __import__("datetime").datetime.now(tz=timezone.utc)
                - timedelta(hours=2)
            )
            expired = create_access_token(
                user_id=sample_user.id,
                role=sample_user.role,
                scopes=sample_user.scopes,
            )
        resp = await client.get(
            "/v1/users/me",
            headers={"Authorization": f"Bearer {expired}"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "TOKEN_EXPIRED"
