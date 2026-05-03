"""
tests/integration/test_github_integration_endpoints.py
──────────────────────────────────────────────────────
Integration tests for GitHub connection and repository sync endpoints.
"""

import pytest
from httpx import AsyncClient

from app.api.dependencies import get_github_integration_service
from app.models.user import User
from app.services.github_integration_service import GithubIntegrationService


class FakeGithubApiClient:
    async def exchange_code_for_token(self, *, code: str, redirect_uri: str):
        assert code == "github_oauth_code"
        assert redirect_uri == "http://localhost:3000/repositories/github/callback"
        return {
            "access_token": "github-access-token",
            "scope": "repo,read:user,user:email",
        }

    async def fetch_user(self, access_token: str):
        assert access_token == "github-access-token"
        return {
            "login": "octocat",
            "id": 123456,
        }

    async def fetch_repositories(self, access_token: str):
        assert access_token == "github-access-token"
        return [
            {
                "id": 99887766,
                "name": "repo-insight-ui",
                "full_name": "octocat/repo-insight-ui",
                "description": "Frontend app",
                "private": True,
                "default_branch": "main",
                "language": "TypeScript",
                "stargazers_count": 12,
                "forks_count": 3,
                "updated_at": "2026-05-03T13:10:00Z",
                "owner": {"login": "octocat"},
            }
        ]


@pytest.mark.asyncio
class TestGithubIntegrationEndpoints:
    async def _get_access_token(self, client: AsyncClient, user: User) -> str:
        response = await client.post(
            "/v1/auth/login",
            json={"email": user.email, "password": "SecurePass1!"},
        )
        assert response.status_code == 200
        return response.json()["access_token"]

    async def _override_github_service(self, db_session):
        async def override():
            return GithubIntegrationService(db_session, github_client=FakeGithubApiClient())

        return override

    async def test_status_returns_disconnected_when_no_connection(
        self,
        client: AsyncClient,
        sample_user: User,
        db_session,
    ):
        token = await self._get_access_token(client, sample_user)
        app_override = await self._override_github_service(db_session)
        client._transport.app.dependency_overrides[get_github_integration_service] = app_override

        response = await client.get(
            "/v1/integrations/github/status",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "connected": False,
            "provider": "github",
            "github_login": None,
            "github_user_id": None,
            "installation_id": None,
            "scopes": [],
            "connected_at": None,
            "last_synced_at": None,
            "sync_status": "never_synced",
        }

    async def test_github_connect_and_sync_flow(
        self,
        client: AsyncClient,
        sample_user: User,
        db_session,
    ):
        token = await self._get_access_token(client, sample_user)
        app_override = await self._override_github_service(db_session)
        client._transport.app.dependency_overrides[get_github_integration_service] = app_override
        headers = {"Authorization": f"Bearer {token}"}

        start_response = await client.post(
            "/v1/integrations/github/connect/start",
            headers=headers,
            json={
                "redirect_uri": "http://localhost:3000/repositories/github/callback",
                "provider_mode": "oauth",
            },
        )
        assert start_response.status_code == 200
        start_data = start_response.json()
        assert "https://github.com/login/oauth/authorize" in start_data["authorize_url"]
        assert start_data["state"]

        callback_response = await client.post(
            "/v1/integrations/github/connect/callback",
            headers=headers,
            json={
                "code": "github_oauth_code",
                "state": start_data["state"],
                "installation_id": None,
            },
        )
        assert callback_response.status_code == 200
        callback_data = callback_response.json()
        assert callback_data["connected"] is True
        assert callback_data["github_login"] == "octocat"
        assert callback_data["github_user_id"] == "123456"
        assert callback_data["sync_status"] == "pending"
        assert callback_data["scopes"] == ["repo", "read:user", "user:email"]

        repositories_response = await client.get(
            "/v1/integrations/github/repositories",
            headers=headers,
        )
        assert repositories_response.status_code == 200
        repositories_data = repositories_response.json()
        assert repositories_data["items"] == [
            {
                "id": "github_repo_99887766",
                "provider_repo_id": "99887766",
                "owner": "octocat",
                "name": "repo-insight-ui",
                "full_name": "octocat/repo-insight-ui",
                "description": "Frontend app",
                "visibility": "private",
                "default_branch": "main",
                "language": "TypeScript",
                "stars": 12,
                "forks": 3,
                "last_updated": "2026-05-03T13:10:00Z",
                "already_synced": False,
            }
        ]

        sync_response = await client.post(
            "/v1/repositories/sync",
            headers=headers,
            json={
                "full_resync": False,
                "repository_ids": ["github_repo_99887766"],
                "source": "manual",
            },
        )
        assert sync_response.status_code == 200
        sync_data = sync_response.json()
        assert sync_data["id"].startswith("sync_job_")
        assert sync_data["status"] == "completed"
        assert sync_data["source"] == "manual"
        assert sync_data["total_repositories"] == 1
        assert sync_data["synced_repositories"] == 1
        assert sync_data["failed_repositories"] == 0
        assert sync_data["started_at"] is not None
        assert sync_data["completed_at"] is not None
        assert sync_data["error_message"] is None

        persisted_response = await client.get("/v1/repositories", headers=headers)
        assert persisted_response.status_code == 200
        persisted_data = persisted_response.json()
        assert persisted_data["page"] == 1
        assert persisted_data["page_size"] == 24
        assert persisted_data["total"] == 1
        assert persisted_data["items"] == [
            {
                "id": "repo_github_99887766",
                "provider": "github",
                "provider_repo_id": "99887766",
                "owner": "octocat",
                "name": "repo-insight-ui",
                "full_name": "octocat/repo-insight-ui",
                "description": "Frontend app",
                "visibility": "private",
                "branch": "main",
                "language": "TypeScript",
                "stars": 12,
                "forks": 3,
                "last_updated": "2026-05-03T13:10:00Z",
                "sync_status": "synced",
                "tree_sha": None,
                "indexed_file_count": 0,
                "default_analysis_status": "completed",
            }
        ]

        status_response = await client.get(
            "/v1/integrations/github/status",
            headers=headers,
        )
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["connected"] is True
        assert status_data["sync_status"] == "synced"
        assert status_data["last_synced_at"] is not None
