"""
tests/conftest.py
──────────────────
Shared pytest fixtures: test DB session, test client, mock Redis, sample users.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models.github_connection import GithubConnection
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.models.repository import Repository
from app.models.repository_sync_job import RepositorySyncJob

# ── Test database (SQLite in-memory for speed) ────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def jwt_test_keys(tmp_path_factory):
    """Generate disposable RSA keys for JWT tests."""
    key_dir = tmp_path_factory.mktemp("jwt_keys")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    private_path = Path(key_dir / "private.pem")
    public_path = Path(key_dir / "public.pem")

    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    settings.JWT_PRIVATE_KEY_PATH = str(private_path)
    settings.JWT_PUBLIC_KEY_PATH = str(public_path)


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional test session that rolls back after each test."""
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client with DB session overridden."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # Mock Redis to avoid requiring a real Redis connection in unit tests
    with patch("app.api.middleware.rate_limiter.get_redis", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = AsyncMock(
            pipeline=MagicMock(return_value=MagicMock(
                zremrangebyscore=MagicMock(),
                zadd=MagicMock(),
                zcard=MagicMock(),
                expire=MagicMock(),
                execute=AsyncMock(return_value=[None, None, 1, None]),
            )),
            ping=AsyncMock(return_value=True),
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

    app.dependency_overrides.clear()


# ── Sample data fixtures ──────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def sample_user(db_session: AsyncSession) -> User:
    """A plain user with a known password."""
    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        hashed_password=hash_password("SecurePass1!"),
        is_verified=True,
        is_active=True,
        role="user",
        scopes=["read:own"],
        subscription_type="free",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        hashed_password=hash_password("AdminPass1!"),
        is_verified=True,
        is_active=True,
        role="admin",
        scopes=["read:own", "read:all", "write:all", "delete:all"],
        subscription_type="enterprise",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def locked_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="locked@example.com",
        hashed_password=hash_password("SecurePass1!"),
        is_verified=True,
        is_active=True,
        role="user",
        scopes=[],
        subscription_type="free",
        failed_login_attempts=5,
        locked_until=datetime.now(tz=timezone.utc) + timedelta(minutes=30),
    )
    db_session.add(user)
    await db_session.flush()
    return user
