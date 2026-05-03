"""
app/api/dependencies.py
────────────────────────
FastAPI injectable dependencies:
  • get_current_user  – validates Bearer token, returns User
  • require_role      – RBAC role guard
  • require_scopes    – scope-based authorization guard
  • get_auth_service  – service factory wired to the request's DB session
"""

from typing import List, Optional
from uuid import UUID

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import (
    InsufficientScopesError,
    InvalidTokenError,
    PermissionDeniedError,
    UserNotFoundError,
)
from app.core.logging import get_logger
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.github_integration_service import GithubIntegrationService

logger = get_logger(__name__)

# HTTPBearer extracts "Bearer <token>" from the Authorization header
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency that:
      1. Extracts the Bearer token from Authorization header
      2. Verifies the JWT signature and expiry
      3. Loads and returns the User from DB

    Raises InvalidTokenError / UserNotFoundError on failure.
    """
    if credentials is None:
        raise InvalidTokenError("Missing Authorization header")

    payload = decode_access_token(credentials.credentials)
    user_id = UUID(payload["sub"])

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if not user or not user.is_active:
        raise UserNotFoundError("User not found or inactive")

    return user


def require_role(*roles: str):
    """
    Dependency factory for role-based access control.

    Usage:
        @router.get("/admin", dependencies=[Depends(require_role("admin"))])
    """
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise PermissionDeniedError(
                f"Role '{current_user.role}' is not permitted. "
                f"Required: {list(roles)}"
            )
        return current_user

    return _check


def require_scopes(*required_scopes: str):
    """
    Dependency factory for scope-based authorization.

    Usage:
        @router.delete("/resource", dependencies=[Depends(require_scopes("delete:resource"))])
    """
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        user_scopes = set(current_user.scopes)
        missing = set(required_scopes) - user_scopes
        if missing:
            raise InsufficientScopesError(
                f"Missing required scopes: {missing}"
            )
        return current_user

    return _check


async def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    """Provide a fully wired AuthService instance."""
    return AuthService(db)


async def get_github_integration_service(
    db: AsyncSession = Depends(get_db),
) -> GithubIntegrationService:
    """Provide the GitHub integration service."""
    return GithubIntegrationService(db)


def get_client_ip(request: Request) -> str:
    """Extract the real client IP, accounting for reverse proxies."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def get_device_info(user_agent: Optional[str] = Header(None)) -> Optional[str]:
    """Extract device info from User-Agent header (truncated for storage)."""
    if user_agent:
        return user_agent[:255]
    return None
