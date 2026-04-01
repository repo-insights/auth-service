"""User service — all DB operations for the users table."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.database import execute, fetch_all, fetch_one
from app.schemas.schemas import UserCreate, UserUpdate

_NOW = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    return await fetch_one("SELECT * FROM users WHERE id = ? AND deleted_at IS NULL", [user_id])


async def get_user_by_email(email: str, tenant_id: str) -> dict[str, Any] | None:
    return await fetch_one(
        "SELECT * FROM users WHERE email = ? AND tenant_id = ? AND deleted_at IS NULL",
        [email, tenant_id],
    )


async def get_user_by_google_id(google_id: str) -> dict[str, Any] | None:
    return await fetch_one(
        "SELECT * FROM users WHERE google_id = ? AND deleted_at IS NULL",
        [google_id],
    )


async def create_user(data: UserCreate) -> dict[str, Any]:
    user_id = str(uuid.uuid4())
    now = _NOW()
    await execute(
        """
        INSERT INTO users
            (id, tenant_id, email, name, password_hash, auth_provider, google_id,
             is_email_verified, role, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            user_id,
            data.tenant_id,
            data.email,
            data.name,
            data.password_hash,
            data.auth_provider,
            data.google_id,
            1 if data.is_email_verified else 0,
            data.role,
            now,
            now,
        ],
    )
    return await get_user_by_id(user_id)  # type: ignore[return-value]


async def update_user(user_id: str, data: UserUpdate) -> dict[str, Any] | None:
    sets, args = [], []
    if data.name is not None:
        sets.append("name = ?"); args.append(data.name)
    if data.avatar_url is not None:
        sets.append("avatar_url = ?"); args.append(data.avatar_url)
    if not sets:
        return await get_user_by_id(user_id)
    sets.append("updated_at = ?"); args.append(_NOW())
    args.append(user_id)
    await execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", args)
    return await get_user_by_id(user_id)


async def soft_delete_user(user_id: str) -> None:
    now = _NOW()
    await execute(
        "UPDATE users SET deleted_at = ?, is_active = 0, updated_at = ? WHERE id = ?",
        [now, now, user_id],
    )


async def mark_email_verified(user_id: str) -> None:
    await execute(
        "UPDATE users SET is_email_verified = 1, updated_at = ? WHERE id = ?",
        [_NOW(), user_id],
    )


async def increment_token_version(user_id: str) -> int:
    """Bump token_version — invalidates all existing JWTs for this user."""
    await execute(
        "UPDATE users SET token_version = token_version + 1, updated_at = ? WHERE id = ?",
        [_NOW(), user_id],
    )
    user = await get_user_by_id(user_id)
    return user["token_version"]  # type: ignore[index]


async def set_razorpay_customer(user_id: str, customer_id: str) -> None:
    await execute(
        "UPDATE users SET razorpay_customer_id = ?, updated_at = ? WHERE id = ?",
        [customer_id, _NOW(), user_id],
    )


async def get_users_by_tenant(tenant_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    return await fetch_all(
        "SELECT * FROM users WHERE tenant_id = ? AND deleted_at IS NULL LIMIT ? OFFSET ?",
        [tenant_id, limit, offset],
    )
