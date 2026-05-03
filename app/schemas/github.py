"""
app/schemas/github.py
─────────────────────
Pydantic schemas for GitHub integration and repository sync endpoints.
"""

from datetime import datetime, timezone

from pydantic import BaseModel, Field, HttpUrl, field_serializer


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class GithubConnectionStatus(BaseModel):
    connected: bool
    provider: str = "github"
    github_login: str | None = None
    github_user_id: str | None = None
    installation_id: str | None = None
    scopes: list[str] = Field(default_factory=list)
    connected_at: datetime | None = None
    last_synced_at: datetime | None = None
    sync_status: str

    @field_serializer("connected_at", "last_synced_at", when_used="json")
    def serialize_datetimes(self, value: datetime | None) -> str | None:
        return _serialize_datetime(value)


class GithubConnectStartRequest(BaseModel):
    redirect_uri: HttpUrl | str
    provider_mode: str = Field(default="oauth")


class GithubConnectStartResponse(BaseModel):
    authorize_url: str
    state: str


class GithubConnectCallbackRequest(BaseModel):
    code: str
    state: str
    installation_id: str | None = None


class GithubRepositoryCandidate(BaseModel):
    id: str
    provider_repo_id: str | None = None
    owner: str
    name: str
    full_name: str
    description: str | None = None
    visibility: str
    default_branch: str | None = None
    language: str | None = None
    stars: int = 0
    forks: int = 0
    last_updated: datetime | None = None
    already_synced: bool

    @field_serializer("last_updated", when_used="json")
    def serialize_last_updated(self, value: datetime | None) -> str | None:
        return _serialize_datetime(value)


class GithubRepositoryCandidateListResponse(BaseModel):
    items: list[GithubRepositoryCandidate]


class RepositorySyncRequest(BaseModel):
    full_resync: bool = False
    repository_ids: list[str] = Field(default_factory=list)
    source: str = "manual"


class SyncJobResponse(BaseModel):
    id: str
    status: str
    source: str
    total_repositories: int | None = None
    synced_repositories: int | None = None
    failed_repositories: int | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}

    @field_serializer("created_at", "started_at", "completed_at", when_used="json")
    def serialize_datetimes(self, value: datetime | None) -> str | None:
        return _serialize_datetime(value)


class RepositoryResponse(BaseModel):
    id: str
    provider: str
    provider_repo_id: str | None = None
    owner: str
    name: str
    full_name: str
    description: str | None = None
    visibility: str
    branch: str | None = None
    language: str | None = None
    stars: int
    forks: int
    last_updated: datetime | None = None
    sync_status: str
    tree_sha: str | None = None
    indexed_file_count: int
    default_analysis_status: str

    model_config = {"from_attributes": True}

    @field_serializer("last_updated", when_used="json")
    def serialize_last_updated(self, value: datetime | None) -> str | None:
        return _serialize_datetime(value)


class RepositoryListResponse(BaseModel):
    items: list[RepositoryResponse]
    page: int
    page_size: int
    total: int
