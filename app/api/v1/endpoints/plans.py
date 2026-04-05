"""Plan and subscription endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_current_active_user
from app.schemas.schemas import PlanResponse, SubscriptionResponse
from app.services import tenant_service

router = APIRouter(prefix="/plans", tags=["Plans & Subscriptions"])


@router.get("/", response_model=list[PlanResponse])
async def list_plans() -> list[dict]:
    return await tenant_service.list_active_plans()


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_my_subscription(current_user: dict = Depends(get_current_active_user)) -> dict:
    sub = await tenant_service.get_active_subscription(current_user["tenant_id"])
    if not sub:
        raise HTTPException(status_code=404, detail="No active subscription found")
    return {
        "id": sub["id"],
        "tenant_id": sub["tenant_id"],
        "plan_id": sub["plan_id"],
        "plan_code": sub["plan_code"],
        "plan_name": sub["plan_name"],
        "description": sub["description"],
        "button_text": sub["button_text"],
        "features": sub["features"],
        "permissions": sub["permissions"],
        "max_repos": sub["max_repos"],
        "max_members": sub["max_members"],
        "is_popular": bool(sub["is_popular"]),
        "status": sub["status"],
        "current_period_end": sub.get("current_period_end"),
    }
