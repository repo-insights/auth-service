"""
app/api/v1/endpoints/integrations.py
─────────────────────────────────────
GitHub integration endpoints.
"""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user, get_github_integration_service
from app.models.user import User
from app.schemas.github import (
    GithubConnectCallbackRequest,
    GithubConnectStartRequest,
    GithubConnectStartResponse,
    GithubConnectionStatus,
    GithubRepositoryCandidateListResponse,
)
from app.services.github_integration_service import GithubIntegrationService

router = APIRouter(prefix="/integrations/github", tags=["GitHub Integrations"])


@router.get("/status", response_model=GithubConnectionStatus, summary="Get GitHub connection status")
async def get_github_status(
    current_user: User = Depends(get_current_user),
    github_service: GithubIntegrationService = Depends(get_github_integration_service),
) -> GithubConnectionStatus:
    return await github_service.get_status(current_user)


@router.post(
    "/connect/start",
    response_model=GithubConnectStartResponse,
    summary="Create a GitHub authorization URL",
)
async def start_github_connect(
    body: GithubConnectStartRequest,
    current_user: User = Depends(get_current_user),
    github_service: GithubIntegrationService = Depends(get_github_integration_service),
) -> GithubConnectStartResponse:
    return await github_service.start_connection(
        user=current_user,
        redirect_uri=str(body.redirect_uri),
        provider_mode=body.provider_mode,
    )


@router.post(
    "/connect/callback",
    response_model=GithubConnectionStatus,
    summary="Exchange GitHub code and store the connection",
)
async def complete_github_connect(
    body: GithubConnectCallbackRequest,
    current_user: User = Depends(get_current_user),
    github_service: GithubIntegrationService = Depends(get_github_integration_service),
) -> GithubConnectionStatus:
    return await github_service.complete_connection(
        user=current_user,
        code=body.code,
        state=body.state,
        installation_id=body.installation_id,
    )


@router.get(
    "/repositories",
    response_model=GithubRepositoryCandidateListResponse,
    summary="List GitHub repositories available for sync",
)
async def list_github_repositories(
    current_user: User = Depends(get_current_user),
    github_service: GithubIntegrationService = Depends(get_github_integration_service),
) -> GithubRepositoryCandidateListResponse:
    return await github_service.list_github_repositories(user=current_user)
