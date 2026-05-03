"""
app/api/v1/endpoints/repositories.py
────────────────────────────────────
Repository sync and listing endpoints.
"""

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_current_user, get_github_integration_service
from app.models.user import User
from app.schemas.github import (
    RepositoryListResponse,
    RepositorySyncRequest,
    SyncJobResponse,
)
from app.services.github_integration_service import GithubIntegrationService

router = APIRouter(prefix="/repositories", tags=["Repositories"])


@router.post("/sync", response_model=SyncJobResponse, summary="Sync selected repositories")
async def sync_repositories(
    body: RepositorySyncRequest,
    current_user: User = Depends(get_current_user),
    github_service: GithubIntegrationService = Depends(get_github_integration_service),
) -> SyncJobResponse:
    return await github_service.sync_repositories(user=current_user, body=body)


@router.get("", response_model=RepositoryListResponse, summary="List persisted repositories")
async def list_repositories(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    github_service: GithubIntegrationService = Depends(get_github_integration_service),
) -> RepositoryListResponse:
    return await github_service.list_persisted_repositories(
        user=current_user,
        page=page,
        page_size=page_size,
    )
