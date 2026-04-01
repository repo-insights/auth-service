"""Tenant service — create and query tenants."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.database import execute, fetch_one

_NOW = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


async def create_tenant(name: str) -> dict[str, Any]:
    tenant_id = str(uuid.uuid4())
    slug = _slugify(name)
    now = _NOW()

    # Ensure slug uniqueness
    existing = await fetch_one("SELECT id FROM tenants WHERE slug = ?", [slug])
    if existing:
        slug = f"{slug}-{tenant_id[:8]}"

    await execute(
        "INSERT INTO tenants (id, name, slug, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        [tenant_id, name, slug, now, now],
    )
    return await get_tenant_by_id(tenant_id)  # type: ignore[return-value]


async def get_tenant_by_id(tenant_id: str) -> dict[str, Any] | None:
    return await fetch_one("SELECT * FROM tenants WHERE id = ?", [tenant_id])


async def get_tenant_by_slug(slug: str) -> dict[str, Any] | None:
    return await fetch_one("SELECT * FROM tenants WHERE slug = ?", [slug])


async def get_active_subscription(tenant_id: str) -> dict[str, Any] | None:
    return await fetch_one(
        """
        SELECT s.*, p.name AS plan_name, p.permissions AS plan_permissions
        FROM subscriptions s
        JOIN plans p ON p.id = s.plan_id
        WHERE s.tenant_id = ? AND s.status = 'active'
        ORDER BY s.created_at DESC
        LIMIT 1
        """,
        [tenant_id],
    )


async def create_default_subscription(tenant_id: str) -> None:
    import uuid as _uuid
    from app.db.database import execute as _exec
    now = _NOW()
    await _exec(
        """
        INSERT INTO subscriptions (id, tenant_id, plan_id, status, created_at, updated_at)
        VALUES (?, ?, 'plan_tier1', 'active', ?, ?)
        """,
        [str(_uuid.uuid4()), tenant_id, now, now],
    )
