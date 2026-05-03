"""
app/repositories/github_connection_repository.py
────────────────────────────────────────────────
Data access layer for GitHub connection records.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.github_connection import GithubConnection


class GithubConnectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_user(self, user_id: UUID) -> GithubConnection | None:
        result = await self._session.execute(
            select(GithubConnection).where(
                GithubConnection.user_id == user_id,
                GithubConnection.provider == "github",
            )
        )
        return result.scalar_one_or_none()

    async def upsert_connection(
        self,
        *,
        user_id: UUID,
        github_login: str,
        github_user_id: str,
        access_token: str,
        scopes: list[str],
        installation_id: str | None,
    ) -> GithubConnection:
        connection = await self.get_for_user(user_id)
        now = datetime.now(tz=timezone.utc)
        if not connection:
            connection = GithubConnection(
                user_id=user_id,
                provider="github",
                sync_status="pending",
            )
            self._session.add(connection)

        connection.github_login = github_login
        connection.github_user_id = github_user_id
        connection.access_token = access_token
        connection.scopes = scopes
        connection.installation_id = installation_id
        connection.connected_at = now
        connection.sync_status = "pending"
        await self._session.flush()
        return connection

    async def update_sync_status(
        self,
        connection: GithubConnection,
        *,
        sync_status: str,
        last_synced_at: datetime | None = None,
    ) -> GithubConnection:
        connection.sync_status = sync_status
        connection.last_synced_at = last_synced_at
        await self._session.flush()
        return connection

