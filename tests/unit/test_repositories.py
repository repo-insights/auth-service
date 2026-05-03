"""
tests/unit/test_repositories.py
────────────────────────────────
Unit tests for UserRepository and TokenRepository using an async SQLite
in-memory database (via fixtures from conftest.py).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User
from app.repositories.token_repository import TokenRepository, _hash_token
from app.repositories.user_repository import UserRepository


# ── UserRepository tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestUserRepository:

    async def test_create_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(
            email="repo_test@example.com",
            hashed_password=hash_password("Password1!"),
        )
        assert user.id is not None
        assert user.email == "repo_test@example.com"
        assert user.role == "user"
        assert user.is_active is True

    async def test_email_is_lowercased(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(email="Upper@Example.COM", hashed_password=None)
        assert user.email == "upper@example.com"

    async def test_get_by_id(self, db_session: AsyncSession, sample_user: User):
        repo = UserRepository(db_session)
        found = await repo.get_by_id(sample_user.id)
        assert found is not None
        assert found.id == sample_user.id

    async def test_get_by_id_nonexistent(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        result = await repo.get_by_id(uuid.uuid4())
        assert result is None

    async def test_get_by_email(self, db_session: AsyncSession, sample_user: User):
        repo = UserRepository(db_session)
        found = await repo.get_by_email(sample_user.email)
        assert found is not None
        assert found.email == sample_user.email

    async def test_get_by_email_case_insensitive(self, db_session: AsyncSession, sample_user: User):
        repo = UserRepository(db_session)
        found = await repo.get_by_email(sample_user.email.upper())
        assert found is not None

    async def test_get_by_email_nonexistent(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        result = await repo.get_by_email("nobody@example.com")
        assert result is None

    async def test_increment_failed_login(self, db_session: AsyncSession, sample_user: User):
        repo = UserRepository(db_session)
        initial = sample_user.failed_login_attempts
        await repo.increment_failed_login(sample_user)
        assert sample_user.failed_login_attempts == initial + 1

    async def test_account_locks_after_max_attempts(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(email="lockme@example.com", hashed_password="x")
        user.failed_login_attempts = 4  # one away from lock

        await repo.increment_failed_login(user)

        assert user.failed_login_attempts == 5
        assert user.locked_until is not None
        assert user.is_locked is True

    async def test_reset_failed_login(self, db_session: AsyncSession, locked_user: User):
        repo = UserRepository(db_session)
        await repo.reset_failed_login(locked_user)
        assert locked_user.failed_login_attempts == 0
        assert locked_user.locked_until is None
        assert locked_user.is_locked is False

    async def test_create_google_user(self, db_session: AsyncSession):
        repo = UserRepository(db_session)
        user = await repo.create(
            email="google@example.com",
            google_id="google_sub_12345",
            is_verified=True,
        )
        assert user.google_id == "google_sub_12345"
        assert user.is_verified is True
        assert user.hashed_password is None


# ── TokenRepository tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestTokenRepository:

    async def test_create_token(self, db_session: AsyncSession, sample_user: User):
        repo = TokenRepository(db_session)
        raw = "raw_refresh_token_value_abc123"
        token = await repo.create(
            user_id=sample_user.id,
            raw_token=raw,
            device_info="Test Device",
            ip_address="127.0.0.1",
        )
        assert token.id is not None
        assert token.user_id == sample_user.id
        # Confirm raw value is NOT stored
        assert token.token_hash != raw
        assert token.token_hash == _hash_token(raw)
        assert token.is_revoked is False

    async def test_get_by_raw_token(self, db_session: AsyncSession, sample_user: User):
        repo = TokenRepository(db_session)
        raw = "findable_token_xyz"
        await repo.create(user_id=sample_user.id, raw_token=raw)
        found = await repo.get_by_raw_token(raw)
        assert found is not None
        assert found.user_id == sample_user.id

    async def test_get_nonexistent_token(self, db_session: AsyncSession):
        repo = TokenRepository(db_session)
        result = await repo.get_by_raw_token("does_not_exist")
        assert result is None

    async def test_revoked_token_not_retrievable(self, db_session: AsyncSession, sample_user: User):
        repo = TokenRepository(db_session)
        raw = "token_to_revoke"
        token = await repo.create(user_id=sample_user.id, raw_token=raw)
        await repo.revoke(token)

        found = await repo.get_by_raw_token(raw)
        assert found is None

    async def test_revoke_all_for_user(self, db_session: AsyncSession, sample_user: User):
        repo = TokenRepository(db_session)
        raw1, raw2 = "multi_token_1", "multi_token_2"
        await repo.create(user_id=sample_user.id, raw_token=raw1)
        await repo.create(user_id=sample_user.id, raw_token=raw2)

        await repo.revoke_all_for_user(sample_user.id)

        assert await repo.get_by_raw_token(raw1) is None
        assert await repo.get_by_raw_token(raw2) is None

    async def test_token_hash_is_deterministic(self):
        raw = "test_value"
        assert _hash_token(raw) == _hash_token(raw)

    async def test_different_tokens_different_hashes(self):
        assert _hash_token("token_a") != _hash_token("token_b")
