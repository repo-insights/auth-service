"""
tests/unit/test_auth_service.py
────────────────────────────────
Unit tests for AuthService business logic.
Repositories and external services are mocked to isolate the service layer.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import (
    AccountLockedError,
    EmailAlreadyExistsError,
    GoogleAuthError,
    InvalidCredentialsError,
    RefreshTokenRevokedError,
)
from app.core.security import create_refresh_token, hash_password
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.services.auth_service import AuthService


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_user(**kwargs) -> User:
    defaults = dict(
        id=uuid.uuid4(),
        email="user@example.com",
        hashed_password=hash_password("SecurePass1!"),
        is_verified=True,
        is_active=True,
        role="user",
        scopes=["read:own"],
        subscription_type="free",
        failed_login_attempts=0,
        locked_until=None,
    )
    defaults.update(kwargs)
    user = User()
    for k, v in defaults.items():
        setattr(user, k, v)
    return user


def _make_token(user_id: uuid.UUID, raw: str) -> RefreshToken:
    token = RefreshToken()
    token.id = uuid.uuid4()
    token.user_id = user_id
    token.is_revoked = False
    token.expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=24)
    return token


def _make_service() -> tuple[AuthService, MagicMock, MagicMock]:
    """Return (service, user_repo_mock, token_repo_mock)."""
    session = AsyncMock()
    service = AuthService(session)

    user_repo = AsyncMock()
    token_repo = AsyncMock()

    service._user_repo = user_repo
    service._token_repo = token_repo

    return service, user_repo, token_repo


# ── Signup ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAuthServiceSignup:

    async def test_signup_creates_user_and_returns_tokens(self):
        service, user_repo, token_repo = _make_service()
        new_user = _make_user()

        user_repo.get_by_email.return_value = None
        user_repo.create.return_value = new_user
        token_repo.create.return_value = _make_token(new_user.id, "raw")

        user, tokens = await service.signup(
            email="new@example.com", password="StrongPass1!"
        )

        user_repo.create.assert_called_once()
        assert user is new_user
        assert tokens.access_token
        assert tokens.refresh_token

    async def test_signup_raises_if_email_exists(self):
        service, user_repo, token_repo = _make_service()
        user_repo.get_by_email.return_value = _make_user()

        with pytest.raises(EmailAlreadyExistsError):
            await service.signup(email="existing@example.com", password="StrongPass1!")

        user_repo.create.assert_not_called()


# ── Login ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAuthServiceLogin:

    async def test_login_success_returns_tokens(self):
        service, user_repo, token_repo = _make_service()
        user = _make_user()

        user_repo.get_by_email.return_value = user
        user_repo.reset_failed_login.return_value = None
        token_repo.create.return_value = _make_token(user.id, "raw")

        tokens = await service.login(email=user.email, password="SecurePass1!")

        assert tokens.access_token
        assert tokens.refresh_token
        user_repo.reset_failed_login.assert_called_once_with(user)

    async def test_login_wrong_password_increments_counter(self):
        service, user_repo, token_repo = _make_service()
        user = _make_user(failed_login_attempts=0)

        user_repo.get_by_email.return_value = user
        user_repo.increment_failed_login.return_value = None

        with pytest.raises(InvalidCredentialsError):
            await service.login(email=user.email, password="WrongPassword1!")

        user_repo.increment_failed_login.assert_called_once_with(user)

    async def test_login_nonexistent_user_raises_invalid_credentials(self):
        service, user_repo, _ = _make_service()
        user_repo.get_by_email.return_value = None

        with pytest.raises(InvalidCredentialsError):
            await service.login(email="ghost@example.com", password="Anything1!")

    async def test_login_locked_account_raises(self):
        service, user_repo, _ = _make_service()
        locked = _make_user(
            locked_until=datetime.now(tz=timezone.utc) + timedelta(minutes=15)
        )
        user_repo.get_by_email.return_value = locked

        with pytest.raises(AccountLockedError):
            await service.login(email=locked.email, password="SecurePass1!")


# ── Refresh ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAuthServiceRefresh:

    async def test_refresh_rotates_tokens(self):
        service, user_repo, token_repo = _make_service()
        user = _make_user()
        raw = create_refresh_token(user_id=user.id, session_id="s1")
        stored = _make_token(user.id, raw)

        token_repo.get_by_raw_token.return_value = stored
        user_repo.get_by_id.return_value = user
        token_repo.revoke.return_value = None
        token_repo.create.return_value = _make_token(user.id, "new_raw")

        tokens = await service.refresh_tokens(raw_refresh_token=raw)

        # Old token must be revoked
        token_repo.revoke.assert_called_once_with(stored)
        assert tokens.access_token
        assert tokens.refresh_token

    async def test_refresh_revoked_token_triggers_session_wipe(self):
        service, user_repo, token_repo = _make_service()
        user = _make_user()
        raw = create_refresh_token(user_id=user.id, session_id="s2")

        # Token not found in DB (already revoked)
        token_repo.get_by_raw_token.return_value = None

        with pytest.raises(RefreshTokenRevokedError):
            await service.refresh_tokens(raw_refresh_token=raw)

        # All sessions for the user must be invalidated
        token_repo.revoke_all_for_user.assert_called_once_with(user.id)

    async def test_refresh_invalid_jwt_raises(self):
        service, _, _ = _make_service()

        with pytest.raises(Exception):  # InvalidTokenError or TokenExpiredError
            await service.refresh_tokens(raw_refresh_token="bad.jwt.token")


# ── Logout ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAuthServiceLogout:

    async def test_logout_revokes_token(self):
        service, user_repo, token_repo = _make_service()
        user = _make_user()
        raw = create_refresh_token(user_id=user.id, session_id="s3")
        stored = _make_token(user.id, raw)

        token_repo.get_by_raw_token.return_value = stored

        await service.logout(raw_refresh_token=raw)

        token_repo.revoke.assert_called_once_with(stored)

    async def test_logout_unknown_token_is_noop(self):
        service, _, token_repo = _make_service()
        token_repo.get_by_raw_token.return_value = None

        # Should not raise
        await service.logout(raw_refresh_token="unknown_token")
        token_repo.revoke.assert_not_called()

    async def test_logout_all_revokes_all(self):
        service, _, token_repo = _make_service()
        user_id = uuid.uuid4()

        await service.logout_all_devices(user_id=user_id)

        token_repo.revoke_all_for_user.assert_called_once_with(user_id)
