"""D1-backed auth runtime state for Workers-friendly deployments."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.database import execute, fetch_one


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dt_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


async def blacklist_access_token(jti: str, ttl_seconds: int) -> None:
    expires_at = _now() + timedelta(seconds=max(ttl_seconds, 0))
    await execute(
        """
        INSERT INTO access_token_blacklist (jti, expires_at, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(jti) DO UPDATE SET expires_at = excluded.expires_at
        """,
        [jti, _dt_str(expires_at), _dt_str(_now())],
    )


async def is_access_token_blacklisted(jti: str) -> bool:
    row = await fetch_one(
        """
        SELECT 1
        FROM access_token_blacklist
        WHERE jti = ? AND expires_at > ?
        LIMIT 1
        """,
        [jti, _dt_str(_now())],
    )
    return row is not None


async def check_rate_limit(prefix: str, identifier: str, max_requests: int, window_seconds: int) -> bool:
    """
    Fixed-window rate limiting stored in D1.
    This intentionally mirrors the old Redis behavior closely.
    """
    now = _now()
    window_start = now - timedelta(seconds=window_seconds)
    window_start_str = _dt_str(window_start)
    now_str = _dt_str(now)

    row = await fetch_one(
        """
        SELECT count, window_started_at
        FROM rate_limit_counters
        WHERE prefix = ? AND identifier = ?
        LIMIT 1
        """,
        [prefix, identifier],
    )

    if not row or row["window_started_at"] <= window_start_str:
        await execute(
            """
            INSERT INTO rate_limit_counters (prefix, identifier, count, window_started_at, updated_at)
            VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(prefix, identifier)
            DO UPDATE SET count = 1, window_started_at = excluded.window_started_at, updated_at = excluded.updated_at
            """,
            [prefix, identifier, now_str, now_str],
        )
        return True

    next_count = int(row["count"]) + 1
    await execute(
        """
        UPDATE rate_limit_counters
        SET count = ?, updated_at = ?
        WHERE prefix = ? AND identifier = ?
        """,
        [next_count, now_str, prefix, identifier],
    )
    return next_count <= max_requests
