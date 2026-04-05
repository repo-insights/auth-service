"""Tenant service — create and query tenants."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.database import execute, fetch_all, fetch_one
from fastapi import HTTPException, status

_NOW = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
DEFAULT_PLAN_ID = "plan_tier1"
DEFAULT_PLAN_CODE = "tier_1"
_PLAN_UI_DEFAULTS: dict[str, dict[str, Any]] = {
    "tier_1": {
        "plan_name": "Starter",
        "description": "For individuals getting started with one repository workspace.",
        "button_text": "Get started",
        "features": ["1 repository", "1 member", "Basic repository access"],
        "is_popular": False,
        "sort_order": 1,
    },
    "tier_2": {
        "plan_name": "Professional",
        "description": "For growing teams that need AI and collaboration features.",
        "button_text": "Start free trial",
        "features": ["5 repositories", "5 members", "AI Q&A", "Team collaboration"],
        "is_popular": True,
        "sort_order": 2,
    },
    "tier_3": {
        "plan_name": "Enterprise",
        "description": "For larger organizations managing many repositories and members.",
        "button_text": "Contact sales",
        "features": ["Unlimited repositories", "Unlimited members", "AI Q&A", "Multi-repo insights"],
        "is_popular": False,
        "sort_order": 3,
    },
}

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


def _hydrate_tenant_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    if "email_suffix" not in row:
        row = {**row, "email_suffix": None}
    return row


def _decode_json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


def _hydrate_plan_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None

    hydrated = dict(row)
    if "permissions" in hydrated:
        hydrated["permissions"] = _decode_json_list(hydrated["permissions"])
    if "features" in hydrated:
        hydrated["features"] = _decode_json_list(hydrated["features"])
    if "plan_permissions" in hydrated:
        hydrated["plan_permissions"] = _decode_json_list(hydrated["plan_permissions"])
    if "plan_features" in hydrated:
        hydrated["plan_features"] = _decode_json_list(hydrated["plan_features"])
    plan_code = hydrated.get("name") or hydrated.get("plan_code")
    defaults = _PLAN_UI_DEFAULTS.get(str(plan_code), {})
    if "display_name" in hydrated and "plan_name" not in hydrated:
        hydrated["plan_name"] = hydrated["display_name"]
    if not hydrated.get("plan_name"):
        hydrated["plan_name"] = defaults.get("plan_name", "")
    if not hydrated.get("description"):
        hydrated["description"] = defaults.get("description", "")
    if not hydrated.get("button_text"):
        hydrated["button_text"] = defaults.get("button_text", "Get started")
    if not hydrated.get("features"):
        hydrated["features"] = list(defaults.get("features", []))
    if "is_popular" not in hydrated or hydrated["is_popular"] is None:
        hydrated["is_popular"] = defaults.get("is_popular", False)
    if "sort_order" not in hydrated or hydrated["sort_order"] is None:
        hydrated["sort_order"] = defaults.get("sort_order", 0)
    return hydrated


def _is_missing_plan_metadata_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        needle in message
        for needle in (
            "no such column: description",
            "no such column: button_text",
            "no such column: features",
            "no such column: is_popular",
            "no such column: sort_order",
        )
    )


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

    try:
        await execute(
            """
            INSERT INTO tenants (id, name, slug, email_suffix, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [tenant_id, name, slug, email_suffix, now, now],
        )
    except ValueError as exc:
        if "tenants has no column named email_suffix" not in str(exc):
            raise
        await execute(
            "INSERT INTO tenants (id, name, slug, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            [tenant_id, name, slug, now, now],
        )
    return await get_tenant_by_id(tenant_id)  # type: ignore[return-value]


async def get_tenant_by_id(tenant_id: str) -> dict[str, Any] | None:
    return _hydrate_tenant_row(await fetch_one("SELECT * FROM tenants WHERE id = ?", [tenant_id]))


async def get_tenant_by_slug(slug: str) -> dict[str, Any] | None:
    return _hydrate_tenant_row(await fetch_one("SELECT * FROM tenants WHERE slug = ?", [slug]))


async def get_tenant_by_name(name: str) -> dict[str, Any] | None:
    return await get_tenant_by_slug(_slugify(name))


async def list_active_plans() -> list[dict[str, Any]]:
    try:
        rows = await fetch_all(
            """
            SELECT *
            FROM plans
            WHERE is_active = 1
            ORDER BY sort_order ASC, max_repos ASC, display_name ASC
            """
        )
    except Exception as exc:
        if not _is_missing_plan_metadata_error(exc):
            raise
        rows = await fetch_all(
            """
            SELECT *
            FROM plans
            WHERE is_active = 1
            ORDER BY max_repos ASC, display_name ASC
            """
        )
    return [_hydrate_plan_row(row) for row in rows if row is not None]


async def get_plan_by_id(plan_id: str) -> dict[str, Any] | None:
    return _hydrate_plan_row(await fetch_one("SELECT * FROM plans WHERE id = ? LIMIT 1", [plan_id]))


async def get_plan_by_code(plan_code: str) -> dict[str, Any] | None:
    return _hydrate_plan_row(await fetch_one("SELECT * FROM plans WHERE name = ? LIMIT 1", [plan_code]))


async def get_default_plan() -> dict[str, Any] | None:
    plan = await get_plan_by_id(DEFAULT_PLAN_ID)
    if plan:
        return plan

    plan = await get_plan_by_code(DEFAULT_PLAN_CODE)
    if plan:
        return plan

    try:
        row = await fetch_one(
            """
            SELECT *
            FROM plans
            WHERE is_active = 1
            ORDER BY sort_order ASC, max_repos ASC, display_name ASC
            LIMIT 1
            """
        )
    except Exception as exc:
        if not _is_missing_plan_metadata_error(exc):
            raise
        row = await fetch_one(
            """
            SELECT *
            FROM plans
            WHERE is_active = 1
            ORDER BY max_repos ASC, display_name ASC
            LIMIT 1
            """
        )
    return _hydrate_plan_row(row)


async def get_active_subscription(tenant_id: str) -> dict[str, Any] | None:
    try:
        row = await fetch_one(
            """
            SELECT
                s.*,
                p.name AS plan_code,
                p.display_name AS plan_name,
                p.description AS description,
                p.button_text AS button_text,
                p.features AS features,
                p.permissions AS permissions,
                p.max_repos AS max_repos,
                p.max_members AS max_members,
                p.is_popular AS is_popular,
                p.sort_order AS sort_order
            FROM subscriptions s
            JOIN plans p ON p.id = s.plan_id
            WHERE s.tenant_id = ? AND s.status = 'active'
            ORDER BY s.created_at DESC
            LIMIT 1
            """,
            [tenant_id],
        )
    except Exception as exc:
        if not _is_missing_plan_metadata_error(exc):
            raise
        row = await fetch_one(
            """
            SELECT
                s.*,
                p.name AS plan_code,
                p.display_name AS plan_name,
                p.permissions AS permissions,
                p.max_repos AS max_repos,
                p.max_members AS max_members
            FROM subscriptions s
            JOIN plans p ON p.id = s.plan_id
            WHERE s.tenant_id = ? AND s.status = 'active'
            ORDER BY s.created_at DESC
            LIMIT 1
            """,
            [tenant_id],
        )
    return _hydrate_plan_row(row)


async def create_default_subscription(tenant_id: str) -> None:
    import uuid as _uuid
    from app.db.database import execute as _exec
    now = _NOW()
    await _exec(
        """
        INSERT INTO subscriptions (id, tenant_id, plan_id, status, created_at, updated_at)
        VALUES (?, ?, ?, 'active', ?, ?)
        """,
        [str(_uuid.uuid4()), tenant_id, DEFAULT_PLAN_ID, now, now],
    )
