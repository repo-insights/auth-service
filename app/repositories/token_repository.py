"""
app/repositories/token_repository.py
──────────────────────────────────────
Data access layer for RefreshToken entities.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.refresh_token import RefreshToken


def _hash_token(raw_token: str) -> str:
    """SHA-256 hash a raw token for safe DB storage."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


class TokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: UUID,
        raw_token: str,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> RefreshToken:
        expires_at = datetime.now(tz=timezone.utc) + timedelta(
            hours=settings.REFRESH_TOKEN_EXPIRE_HOURS
        )
        token = RefreshToken(
            user_id=user_id,
            token_hash=_hash_token(raw_token),
            device_info=device_info,
            ip_address=ip_address,
            expires_at=expires_at,
        )
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_by_raw_token(self, raw_token: str) -> Optional[RefreshToken]:
        result = await self._session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == _hash_token(raw_token),
                RefreshToken.is_revoked.is_(False),
                RefreshToken.expires_at > datetime.now(tz=timezone.utc),
            )
        )
        return result.scalar_one_or_none()

    async def revoke(self, token: RefreshToken) -> None:
        """Revoke a specific token (single-session logout)."""
        token.is_revoked = True
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        """Revoke ALL tokens for a user (logout everywhere)."""
        await self._session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.is_revoked.is_(False),
            )
            .values(is_revoked=True)
        )

    async def touch_last_used(self, token: RefreshToken) -> None:
        token.last_used_at = datetime.now(tz=timezone.utc)
        await self._session.flush()

    async def delete_expired(self) -> int:
        """Housekeeping: remove expired tokens. Returns deleted count."""
        result = await self._session.execute(
            delete(RefreshToken).where(
                RefreshToken.expires_at <= datetime.now(tz=timezone.utc)
            )
        )
        return result.rowcount
