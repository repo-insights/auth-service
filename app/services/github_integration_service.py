"""
app/services/github_integration_service.py
──────────────────────────────────────────
Business logic for GitHub connection, repository discovery, and sync flows.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import httpx
from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import AppException, InvalidTokenError, ValidationError
from app.models.user import User
from app.repositories.github_connection_repository import GithubConnectionRepository
from app.repositories.repository_repository import RepositoryRepository
from app.repositories.repository_sync_job_repository import RepositorySyncJobRepository
from app.schemas.github import (
    GithubConnectStartResponse,
    GithubConnectionStatus,
    GithubRepositoryCandidate,
    GithubRepositoryCandidateListResponse,
    RepositoryListResponse,
    RepositorySyncRequest,
    SyncJobResponse,
)


class GithubConnectionRequiredError(AppException):
    status_code = 400
    error_code = "GITHUB_CONNECTION_REQUIRED"
    message = "Connect a GitHub account before performing this action"


class GithubOAuthExchangeError(AppException):
    status_code = 400
    error_code = "GITHUB_OAUTH_ERROR"
    message = "GitHub OAuth exchange failed"


class GithubStateError(InvalidTokenError):
    error_code = "INVALID_GITHUB_STATE"
    message = "GitHub OAuth state is invalid"


class GithubApiClient:
    async def exchange_code_for_token(self, *, code: str, redirect_uri: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
            response.raise_for_status()
            payload = response.json()
            if "error" in payload:
                raise GithubOAuthExchangeError(payload.get("error_description") or payload["error"])
            return payload

    async def fetch_user(self, access_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                },
            )
            response.raise_for_status()
            return response.json()

    async def fetch_repositories(self, access_token: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                "https://api.github.com/user/repos",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                },
                params={
                    "per_page": 100,
                    "sort": "updated",
                    "affiliation": "owner,collaborator,organization_member",
                },
            )
            response.raise_for_status()
            return response.json()


class GithubIntegrationService:
    def __init__(self, session, github_client: GithubApiClient | None = None) -> None:
        self._connection_repo = GithubConnectionRepository(session)
        self._repository_repo = RepositoryRepository(session)
        self._sync_job_repo = RepositorySyncJobRepository(session)
        self._github_client = github_client or GithubApiClient()

    def _create_state(self, *, user_id: UUID, redirect_uri: str, provider_mode: str) -> str:
        now = datetime.now(tz=timezone.utc)
        payload = {
            "sub": str(user_id),
            "redirect_uri": redirect_uri,
            "provider_mode": provider_mode,
            "nonce": secrets.token_urlsafe(16),
            "iat": now,
            "exp": now + timedelta(minutes=10),
        }
        return jwt.encode(payload, settings.jwt_private_key, algorithm=settings.JWT_ALGORITHM)

    def _decode_state(self, state: str) -> dict[str, Any]:
        try:
            payload = jwt.decode(
                state,
                settings.jwt_public_key,
                algorithms=[settings.JWT_ALGORITHM],
            )
        except JWTError as exc:
            raise GithubStateError() from exc
        return payload

    def _build_authorize_url(self, *, redirect_uri: str, state: str, provider_mode: str) -> str:
        scopes = "repo read:user user:email"
        query = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": scopes,
        }
        if provider_mode == "github_app":
            query["allow_signup"] = "false"
        return f"https://github.com/login/oauth/authorize?{urlencode(query)}"

    async def get_status(self, user: User) -> GithubConnectionStatus:
        connection = await self._connection_repo.get_for_user(user.id)
        if not connection or not connection.access_token:
            return GithubConnectionStatus(connected=False, sync_status="never_synced")

        return GithubConnectionStatus(
            connected=True,
            provider=connection.provider,
            github_login=connection.github_login,
            github_user_id=connection.github_user_id,
            installation_id=connection.installation_id,
            scopes=connection.scopes or [],
            connected_at=connection.connected_at,
            last_synced_at=connection.last_synced_at,
            sync_status=connection.sync_status,
        )

    async def start_connection(
        self,
        *,
        user: User,
        redirect_uri: str,
        provider_mode: str,
    ) -> GithubConnectStartResponse:
        if provider_mode not in {"oauth", "github_app"}:
            raise ValidationError("provider_mode must be one of: oauth, github_app")

        state = self._create_state(
            user_id=user.id,
            redirect_uri=redirect_uri,
            provider_mode=provider_mode,
        )
        return GithubConnectStartResponse(
            authorize_url=self._build_authorize_url(
                redirect_uri=redirect_uri,
                state=state,
                provider_mode=provider_mode,
            ),
            state=state,
        )

    async def complete_connection(
        self,
        *,
        user: User,
        code: str,
        state: str,
        installation_id: str | None,
    ) -> GithubConnectionStatus:
        state_payload = self._decode_state(state)
        if state_payload.get("sub") != str(user.id):
            raise GithubStateError("GitHub OAuth state does not belong to the current user")

        token_payload = await self._github_client.exchange_code_for_token(
            code=code,
            redirect_uri=state_payload["redirect_uri"],
        )
        access_token = token_payload["access_token"]
        scopes = [
            scope.strip()
            for scope in (token_payload.get("scope") or "").split(",")
            if scope.strip()
        ]
        github_user = await self._github_client.fetch_user(access_token)
        connection = await self._connection_repo.upsert_connection(
            user_id=user.id,
            github_login=github_user["login"],
            github_user_id=str(github_user["id"]),
            access_token=access_token,
            scopes=scopes,
            installation_id=installation_id,
        )
        return GithubConnectionStatus(
            connected=True,
            provider=connection.provider,
            github_login=connection.github_login,
            github_user_id=connection.github_user_id,
            installation_id=connection.installation_id,
            scopes=connection.scopes,
            connected_at=connection.connected_at,
            last_synced_at=connection.last_synced_at,
            sync_status=connection.sync_status,
        )

    async def list_github_repositories(self, *, user: User) -> GithubRepositoryCandidateListResponse:
        connection = await self._connection_repo.get_for_user(user.id)
        if not connection or not connection.access_token:
            raise GithubConnectionRequiredError()

        remote_repositories = await self._github_client.fetch_repositories(connection.access_token)
        items: list[GithubRepositoryCandidate] = []
        for repo in remote_repositories:
            provider_repo_id = str(repo["id"])
            existing = await self._repository_repo.get_by_provider_repo_id(
                user_id=user.id,
                provider="github",
                provider_repo_id=provider_repo_id,
            )
            items.append(
                GithubRepositoryCandidate(
                    id=f"github_repo_{provider_repo_id}",
                    provider_repo_id=provider_repo_id,
                    owner=repo["owner"]["login"],
                    name=repo["name"],
                    full_name=repo["full_name"],
                    description=repo.get("description"),
                    visibility="private" if repo.get("private") else "public",
                    default_branch=repo.get("default_branch"),
                    language=repo.get("language"),
                    stars=repo.get("stargazers_count", 0),
                    forks=repo.get("forks_count", 0),
                    last_updated=repo.get("updated_at"),
                    already_synced=existing is not None,
                )
            )
        return GithubRepositoryCandidateListResponse(items=items)

    async def sync_repositories(self, *, user: User, body: RepositorySyncRequest) -> SyncJobResponse:
        if not body.repository_ids:
            raise ValidationError("repository_ids must contain at least one repository")

        job = await self._sync_job_repo.create(
            job_id=f"sync_job_{secrets.token_hex(6)}",
            user_id=user.id,
            source=body.source,
            total_repositories=len(body.repository_ids),
        )

        connection = await self._connection_repo.get_for_user(user.id)
        if not connection or not connection.access_token:
            await self._sync_job_repo.mark_failed(job, GithubConnectionRequiredError.message)
            raise GithubConnectionRequiredError()

        await self._sync_job_repo.mark_running(job)
        await self._connection_repo.update_sync_status(connection, sync_status="syncing")

        try:
            candidates = await self.list_github_repositories(user=user)
            candidate_map = {item.id: item for item in candidates.items}
            synced_count = 0
            failed_count = 0

            for repository_id in body.repository_ids:
                candidate = candidate_map.get(repository_id)
                if not candidate:
                    failed_count += 1
                    continue

                await self._repository_repo.upsert_from_candidate(
                    user_id=user.id,
                    candidate_id=candidate.id,
                    provider="github",
                    provider_repo_id=candidate.provider_repo_id,
                    owner=candidate.owner,
                    name=candidate.name,
                    full_name=candidate.full_name,
                    description=candidate.description,
                    visibility=candidate.visibility,
                    branch=candidate.default_branch,
                    language=candidate.language,
                    stars=candidate.stars,
                    forks=candidate.forks,
                    last_updated=candidate.last_updated,
                    full_resync=body.full_resync,
                )
                synced_count += 1

            await self._sync_job_repo.mark_completed(
                job,
                synced_repositories=synced_count,
                failed_repositories=failed_count,
            )
            await self._connection_repo.update_sync_status(
                connection,
                sync_status="synced" if failed_count == 0 else "failed",
                last_synced_at=datetime.now(tz=timezone.utc),
            )
        except Exception as exc:
            await self._sync_job_repo.mark_failed(job, str(exc))
            await self._connection_repo.update_sync_status(connection, sync_status="failed")
            raise

        return SyncJobResponse.model_validate(job)

    async def list_persisted_repositories(
        self,
        *,
        user: User,
        page: int,
        page_size: int,
    ) -> RepositoryListResponse:
        items, total = await self._repository_repo.list_for_user(
            user_id=user.id,
            page=page,
            page_size=page_size,
        )
        return RepositoryListResponse(
            items=[item for item in items],
            page=page,
            page_size=page_size,
            total=total,
        )
