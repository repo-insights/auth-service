"""
app/repositories/repository_sync_job_repository.py
──────────────────────────────────────────────────
Data access layer for repository sync jobs.
"""

from datetime import datetime, timezone
from uuid import UUID

from app.models.repository_sync_job import RepositorySyncJob


class RepositorySyncJobRepository:
    def __init__(self, session) -> None:
        self._session = session

    async def create(
        self,
        *,
        job_id: str,
        user_id: UUID,
        source: str,
        total_repositories: int | None,
    ) -> RepositorySyncJob:
        job = RepositorySyncJob(
            id=job_id,
            user_id=user_id,
            status="queued",
            source=source,
            total_repositories=total_repositories,
            synced_repositories=0,
            failed_repositories=0,
        )
        self._session.add(job)
        await self._session.flush()
        return job

    async def mark_running(self, job: RepositorySyncJob) -> RepositorySyncJob:
        job.status = "running"
        job.started_at = datetime.now(tz=timezone.utc)
        await self._session.flush()
        return job

    async def mark_completed(
        self,
        job: RepositorySyncJob,
        *,
        synced_repositories: int,
        failed_repositories: int,
    ) -> RepositorySyncJob:
        job.status = "completed"
        job.synced_repositories = synced_repositories
        job.failed_repositories = failed_repositories
        job.completed_at = datetime.now(tz=timezone.utc)
        await self._session.flush()
        return job

    async def mark_failed(self, job: RepositorySyncJob, message: str) -> RepositorySyncJob:
        job.status = "failed"
        job.error_message = message
        job.completed_at = datetime.now(tz=timezone.utc)
        await self._session.flush()
        return job
