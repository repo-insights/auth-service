"""Tenant service — create and query tenants."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.database import execute, fetch_one
from fastapi import HTTPException, status

_NOW = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

_PUBLIC_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "icloud.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
}


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def extract_email_domain(email: str) -> str:
    return email.strip().lower().split("@", 1)[-1]


def get_workspace_email_suffix(email: str) -> str | None:
    domain = extract_email_domain(email)
    return None if domain in _PUBLIC_EMAIL_DOMAINS else domain


def can_join_workspace(tenant: dict[str, Any], email: str) -> bool:
    email_suffix = tenant.get("email_suffix")
    return bool(email_suffix and extract_email_domain(email) == email_suffix)


async def create_tenant(name: str, email_suffix: str | None = None) -> dict[str, Any]:
    tenant_id = str(uuid.uuid4())
    slug = _slugify(name)
    now = _NOW()

    existing = await fetch_one("SELECT id FROM tenants WHERE slug = ?", [slug])
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspace name already exists",
        )

    await execute(
        """
        INSERT INTO tenants (id, name, slug, email_suffix, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [tenant_id, name, slug, email_suffix, now, now],
    )
    return await get_tenant_by_id(tenant_id)  # type: ignore[return-value]


async def get_tenant_by_id(tenant_id: str) -> dict[str, Any] | None:
    return await fetch_one("SELECT * FROM tenants WHERE id = ?", [tenant_id])


async def get_tenant_by_slug(slug: str) -> dict[str, Any] | None:
    return await fetch_one("SELECT * FROM tenants WHERE slug = ?", [slug])


async def get_tenant_by_name(name: str) -> dict[str, Any] | None:
    return await get_tenant_by_slug(_slugify(name))


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
