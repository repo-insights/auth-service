"""
app/repositories/user_repository.py
─────────────────────────────────────
Data access layer for User entities.
All DB interactions live here — services never touch SQLAlchemy directly.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        result = await self._session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self._session.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_by_google_id(self, google_id: str) -> Optional[User]:
        result = await self._session.execute(
            select(User).where(User.google_id == google_id)
        )
        return result.scalar_one_or_none()

    # ── Write ─────────────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        email: str,
        hashed_password: Optional[str] = None,
        google_id: Optional[str] = None,
        is_verified: bool = False,
        role: str = "user",
        scopes: Optional[list[str]] = None,
        subscription_type: str = "free",
    ) -> User:
        user = User(
            email=email.lower(),
            hashed_password=hashed_password,
            google_id=google_id,
            is_verified=is_verified,
            role=role,
            scopes=scopes or [],
            subscription_type=subscription_type,
        )
        self._session.add(user)
        await self._session.flush()  # Populate id without committing
        return user

    async def update_password(self, user_id: UUID, hashed_password: str) -> None:
        await self._session.execute(
            update(User)
            .where(User.id == user_id)
            .values(hashed_password=hashed_password)
        )

    async def increment_failed_login(self, user: User) -> None:
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
            user.locked_until = datetime.now(tz=timezone.utc) + timedelta(
                minutes=settings.ACCOUNT_LOCK_MINUTES
            )
        await self._session.flush()

    async def reset_failed_login(self, user: User) -> None:
        user.failed_login_attempts = 0
        user.locked_until = None
        await self._session.flush()

    async def verify_email(self, user_id: UUID) -> None:
        await self._session.execute(
            update(User)
            .where(User.id == user_id)
            .values(is_verified=True)
        )

    async def deactivate(self, user_id: UUID) -> None:
        await self._session.execute(
            update(User)
            .where(User.id == user_id)
            .values(is_active=False)
        )
