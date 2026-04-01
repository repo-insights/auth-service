"""Token service — persists refresh and verification tokens in D1."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.core.security import sha256_hex
from app.db.database import execute, fetch_one

_NOW = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dt_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────────────────────
# Refresh tokens
# ─────────────────────────────────────────

async def store_refresh_token(
    raw_token: str,
    user_id: str,
    token_version: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> str:
    """Persist refresh token metadata to D1. Returns the token jti."""
    jti = str(uuid.uuid4())
    token_hash = sha256_hex(raw_token)
    expire_dt = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_refresh_token_expire_hours)

    await execute(
        """
        INSERT INTO refresh_tokens
            (id, user_id, token_hash, token_version, expires_at, ip_address, user_agent, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [jti, user_id, token_hash, token_version, _dt_str(expire_dt), ip_address, user_agent, _NOW()],
    )
    return jti


async def validate_refresh_token(raw_token: str) -> dict[str, Any] | None:
    """
    Validate a refresh token.
    Checks: hash match, not revoked, not expired, token_version matches user.
    Returns the DB row if valid, None otherwise.
    """
    token_hash = sha256_hex(raw_token)
    row = await fetch_one(
        """
        SELECT rt.*, u.token_version AS user_token_version
        FROM refresh_tokens rt
        JOIN users u ON u.id = rt.user_id
        WHERE rt.token_hash = ?
        """,
        [token_hash],
    )
    if not row:
        return None
    if row["revoked"]:
        return None
    expires_at = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires_at:
        return None
    if row["token_version"] != row["user_token_version"]:
        # Token version mismatch — user force-logged out
        await revoke_refresh_token_by_hash(token_hash)
        return None
    return row


async def revoke_refresh_token_by_hash(token_hash: str) -> None:
    now = _NOW()
    row = await fetch_one("SELECT id FROM refresh_tokens WHERE token_hash = ?", [token_hash])
    if row:
        await execute(
            "UPDATE refresh_tokens SET revoked = 1, revoked_at = ? WHERE token_hash = ?",
            [now, token_hash],
        )


async def revoke_all_refresh_tokens_for_user(user_id: str) -> None:
    """Revoke all active refresh tokens — used on password change / logout-all."""
    rows = await fetch_one(
        "SELECT id FROM refresh_tokens WHERE user_id = ? AND revoked = 0",
        [user_id],
    )
    now = _NOW()
    await execute(
        "UPDATE refresh_tokens SET revoked = 1, revoked_at = ? WHERE user_id = ? AND revoked = 0",
        [now, user_id],
    )


# ─────────────────────────────────────────
# Email verifications
# ─────────────────────────────────────────

async def store_email_verification_token(raw_token: str, user_id: str) -> None:
    token_hash = sha256_hex(raw_token)
    expire_dt = datetime.now(timezone.utc) + timedelta(hours=24)
    jti = str(uuid.uuid4())
    await execute(
        """
        INSERT INTO email_verifications (id, user_id, token_hash, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        [jti, user_id, token_hash, _dt_str(expire_dt), _NOW()],
    )


async def validate_email_verification_token(raw_token: str) -> dict[str, Any] | None:
    token_hash = sha256_hex(raw_token)
    row = await fetch_one(
        "SELECT * FROM email_verifications WHERE token_hash = ?",
        [token_hash],
    )
    if not row:
        return None
    if row["used"]:
        return None
    expires_at = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires_at:
        return None
    # Mark as used
    await execute(
        "UPDATE email_verifications SET used = 1, used_at = ? WHERE token_hash = ?",
        [_NOW(), token_hash],
    )
    return row
