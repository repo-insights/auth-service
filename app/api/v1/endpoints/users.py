"""User endpoints — CRUD, profile management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import assert_same_tenant, get_current_active_user, require_admin
from app.schemas.schemas import ProfileUpdate, UserResponse, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_active_user)) -> dict:
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    data: ProfileUpdate,
    current_user: dict = Depends(get_current_active_user),
) -> dict:
    updated = await user_service.update_user(current_user["id"], UserUpdate(**data.model_dump()))
    return updated


@router.delete("/me", status_code=status.HTTP_200_OK)
async def delete_me(current_user: dict = Depends(get_current_active_user)) -> dict[str, str]:
    await user_service.soft_delete_user(current_user["id"])
    return {"message": "User deleted successfully"}


# ─── Admin endpoints ──────────────────────────────────────────────────────────

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: dict = Depends(require_admin),
) -> dict:
    user = await user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    assert_same_tenant(current_user, user["tenant_id"])
    return user


@router.get("/", response_model=list[UserResponse])
async def list_users(
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(require_admin),
) -> list[dict]:
    return await user_service.get_users_by_tenant(current_user["tenant_id"], limit, offset)


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user(user_id: str, current_user: dict = Depends(require_admin)) -> dict[str, str]:
    user = await user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    assert_same_tenant(current_user, user["tenant_id"])
    await user_service.soft_delete_user(user_id)
    return {"message": "User deleted successfully"}
