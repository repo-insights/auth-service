"""
app/core/redis.py
──────────────────
Async Redis client used for:
  • Rate limiting (request counters per IP)
  • Token blacklist (invalidated access tokens)
  • Account lock state cache
"""

from typing import Optional

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    """Return the shared async Redis client, creating it on first call."""
    global _redis_client
    if _redis_client is None:
        _redis_client = await aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
            health_check_interval=30,
        )
        logger.info("Redis connection established", url=settings.redis_url)
    return _redis_client


async def close_redis() -> None:
    """Close the Redis connection pool (called on app shutdown)."""
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis connection closed")


# ── Key builders (centralise key naming) ─────────────────────────────────────

class RedisKeys:
    @staticmethod
    def rate_limit(identifier: str) -> str:
        return f"rate_limit:{identifier}"

    @staticmethod
    def token_blacklist(jti: str) -> str:
        return f"blacklist:{jti}"

    @staticmethod
    def account_lock(email: str) -> str:
        return f"lock:{email}"

    @staticmethod
    def login_attempts(email: str) -> str:
        return f"attempts:{email}"
