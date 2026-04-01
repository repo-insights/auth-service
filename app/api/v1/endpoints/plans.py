"""Plan and subscription endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_current_active_user
from app.db.database import fetch_all, fetch_one
from app.schemas.schemas import PlanResponse, SubscriptionResponse
from app.services import tenant_service

router = APIRouter(prefix="/plans", tags=["Plans & Subscriptions"])


@router.get("/", response_model=list[PlanResponse])
async def list_plans() -> list[dict]:
    rows = await fetch_all("SELECT * FROM plans WHERE is_active = 1 ORDER BY max_repos")
    for row in rows:
        import json
        row["permissions"] = json.loads(row["permissions"])
    return rows


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_my_subscription(current_user: dict = Depends(get_current_active_user)) -> dict:
    sub = await tenant_service.get_active_subscription(current_user["tenant_id"])
    if not sub:
        raise HTTPException(status_code=404, detail="No active subscription found")
    return {
        "id": sub["id"],
        "tenant_id": sub["tenant_id"],
        "plan_id": sub["plan_id"],
        "plan_name": sub["plan_name"],
        "status": sub["status"],
        "current_period_end": sub.get("current_period_end"),
    }
