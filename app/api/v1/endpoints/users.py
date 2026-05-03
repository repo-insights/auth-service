"""
app/api/v1/endpoints/users.py
──────────────────────────────
User endpoints:
  GET  /users/me         – fetch own profile (requires auth)
  GET  /users/{id}       – fetch user by ID (admin only)
  GET  /users            – list users (admin only)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import (
    get_current_user,
    require_role,
    require_scopes,
)
from app.models.user import User
from app.schemas.auth import UserResponse

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get the authenticated user's profile",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """
    Returns the profile of the currently authenticated user.
    Requires a valid Bearer access token.
    """
    return UserResponse.model_validate(current_user)


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get any user by ID (admin only)",
    dependencies=[Depends(require_role("admin"))],
)
async def get_user_by_id(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """
    Fetch any user by their UUID. Restricted to admin role.

    In a full implementation this would query the UserRepository.
    Shown here as a pattern stub for RBAC demonstration.
    """
    # In production: inject UserRepository and call get_by_id
    # Stub: return self if ID matches (for demo purposes)
    if current_user.id == user_id:
        return UserResponse.model_validate(current_user)

    # Would normally: user = await user_repo.get_by_id(user_id)
    from app.core.exceptions import UserNotFoundError
    raise UserNotFoundError()
