"""Tenant and team endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import assert_same_tenant, get_current_active_user, require_admin
from app.db.database import execute, fetch_all, fetch_one
from app.schemas.schemas import (
    PendingWorkspaceUserResponse,
    TeamCreate,
    TeamMemberAdd,
    TeamResponse,
    TenantResponse,
)
from app.services import tenant_service, user_service

router = APIRouter(tags=["Tenants & Teams"])

_NOW = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─── Tenant ──────────────────────────────────────────────────────────────────

@router.get("/tenants/me", response_model=TenantResponse)
async def get_my_tenant(current_user: dict = Depends(get_current_active_user)) -> dict:
    tenant = await tenant_service.get_tenant_by_id(current_user["tenant_id"])
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


# ─── Teams ───────────────────────────────────────────────────────────────────

teams_router = APIRouter(prefix="/teams", tags=["Tenants & Teams"])


@teams_router.post("/", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    data: TeamCreate,
    current_user: dict = Depends(get_current_active_user),
) -> dict:
    team_id = str(uuid.uuid4())
    now = _NOW()
    await execute(
        """
        INSERT INTO teams (id, tenant_id, name, description, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [team_id, current_user["tenant_id"], data.name, data.description, current_user["id"], now, now],
    )
    # Auto-add creator as lead
    await execute(
        "INSERT INTO user_teams (id, user_id, team_id, role, joined_at) VALUES (?, ?, ?, 'lead', ?)",
        [str(uuid.uuid4()), current_user["id"], team_id, now],
    )
    row = await fetch_one("SELECT * FROM teams WHERE id = ?", [team_id])
    return row


@teams_router.get("/", response_model=list[TeamResponse])
async def list_teams(current_user: dict = Depends(get_current_active_user)) -> list[dict]:
    return await fetch_all(
        "SELECT * FROM teams WHERE tenant_id = ? AND is_active = 1",
        [current_user["tenant_id"]],
    )


@teams_router.get("/pending-users", response_model=list[PendingWorkspaceUserResponse])
async def list_pending_workspace_users(
    current_user: dict = Depends(require_admin),
) -> list[dict]:
    return await user_service.get_pending_workspace_users(current_user["tenant_id"])


@teams_router.post("/members/{user_id}/approve", status_code=status.HTTP_200_OK)
async def approve_workspace_user(
    user_id: str,
    current_user: dict = Depends(require_admin),
) -> dict[str, str]:
    user = await user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    assert_same_tenant(current_user, user["tenant_id"])
    if user["workspace_access_status"] == "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already approved")
    await user_service.approve_workspace_user(user_id, current_user["id"])
    return {"message": "User approved successfully"}


@teams_router.get("/{team_id}", response_model=TeamResponse)
async def get_team(team_id: str, current_user: dict = Depends(get_current_active_user)) -> dict:
    team = await fetch_one("SELECT * FROM teams WHERE id = ?", [team_id])
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    assert_same_tenant(current_user, team["tenant_id"])
    return team


@teams_router.post("/{team_id}/members", status_code=status.HTTP_201_CREATED)
async def add_team_member(
    team_id: str,
    data: TeamMemberAdd,
    current_user: dict = Depends(require_admin),
) -> dict:
    team = await fetch_one("SELECT * FROM teams WHERE id = ?", [team_id])
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    assert_same_tenant(current_user, team["tenant_id"])

    existing = await fetch_one(
        "SELECT id FROM user_teams WHERE user_id = ? AND team_id = ?",
        [data.user_id, team_id],
    )
    if existing:
        raise HTTPException(status_code=409, detail="User already in team")

    await execute(
        "INSERT INTO user_teams (id, user_id, team_id, role, joined_at) VALUES (?, ?, ?, ?, ?)",
        [str(uuid.uuid4()), data.user_id, team_id, data.role, _NOW()],
    )
    return {"message": f"User added to team as {data.role}"}


@teams_router.delete(
    "/{team_id}/members/{user_id}",
    status_code=status.HTTP_200_OK,
)
async def remove_team_member(
    team_id: str,
    user_id: str,
    current_user: dict = Depends(require_admin),
) -> dict[str, str]:
    team = await fetch_one("SELECT * FROM teams WHERE id = ?", [team_id])
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    assert_same_tenant(current_user, team["tenant_id"])
    await execute(
        "DELETE FROM user_teams WHERE user_id = ? AND team_id = ?",
        [user_id, team_id],
    )
    return {"message": "User removed from team"}


router.include_router(teams_router)
