"""
app/repositories/repository_repository.py
─────────────────────────────────────────
Data access for persisted repository rows.
"""

from typing import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repository import Repository


class RepositoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_provider_repo_id(
        self,
        *,
        user_id: UUID,
        provider: str,
        provider_repo_id: str | None,
    ) -> Repository | None:
        if provider_repo_id is None:
            return None

        result = await self._session.execute(
            select(Repository).where(
                Repository.user_id == user_id,
                Repository.provider == provider,
                Repository.provider_repo_id == provider_repo_id,
                Repository.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def upsert_from_candidate(
        self,
        *,
        user_id: UUID,
        candidate_id: str,
        provider: str,
        provider_repo_id: str | None,
        owner: str,
        name: str,
        full_name: str,
        description: str | None,
        visibility: str,
        branch: str | None,
        language: str | None,
        stars: int,
        forks: int,
        last_updated,
        full_resync: bool,
    ) -> Repository:
        repository = await self.get_by_provider_repo_id(
            user_id=user_id,
            provider=provider,
            provider_repo_id=provider_repo_id,
        )
        if not repository:
            repository = Repository(
                id=f"repo_{provider}_{provider_repo_id or candidate_id}",
                user_id=user_id,
                provider=provider,
                provider_repo_id=provider_repo_id,
            )
            self._session.add(repository)

        repository.owner = owner
        repository.name = name
        repository.full_name = full_name
        repository.description = description
        repository.visibility = visibility
        repository.branch = branch
        repository.language = language
        repository.stars = stars
        repository.forks = forks
        repository.last_updated = last_updated
        repository.sync_status = "synced"
        repository.tree_sha = None if full_resync else repository.tree_sha
        repository.indexed_file_count = 0 if full_resync else repository.indexed_file_count
        repository.default_analysis_status = "completed"
        repository.is_deleted = False
        await self._session.flush()
        return repository

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        page: int,
        page_size: int,
    ) -> tuple[Sequence[Repository], int]:
        total_result = await self._session.execute(
            select(func.count()).select_from(Repository).where(
                Repository.user_id == user_id,
                Repository.is_deleted.is_(False),
            )
        )
        total = int(total_result.scalar_one())

        result = await self._session.execute(
            select(Repository)
            .where(
                Repository.user_id == user_id,
                Repository.is_deleted.is_(False),
            )
            .order_by(Repository.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return result.scalars().all(), total

