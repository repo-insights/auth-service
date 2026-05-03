"""
app/api/middleware/rate_limiter.py
───────────────────────────────────
Sliding-window rate limiter using Redis.
Falls back gracefully if Redis is unavailable (allow request, log warning).

Applies per IP address. Auth endpoints get tighter limits.
"""

import time
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.exceptions import RateLimitExceededError
from app.core.logging import get_logger
from app.core.redis import RedisKeys, get_redis

logger = get_logger(__name__)

# Tighter limits for sensitive auth endpoints (per minute)
SENSITIVE_LIMITS: dict[str, int] = {
    "/v1/auth/login": 10,
    "/v1/auth/signup": 5,
    "/v1/auth/google": 10,
    "/v1/auth/refresh": 20,
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, default_limit: int = settings.RATE_LIMIT_PER_MINUTE):
        super().__init__(app)
        self.default_limit = default_limit

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for health checks
        if request.url.path in ("/health", "/metrics"):
            return await call_next(request)

        ip = self._get_ip(request)
        path = request.url.path
        limit = SENSITIVE_LIMITS.get(path, self.default_limit)

        try:
            redis = await get_redis()
            allowed, remaining, reset_in = await self._check_rate_limit(
                redis, ip, path, limit
            )
        except Exception as exc:
            logger.warning("Rate limiter unavailable, allowing request", error=str(exc))
            return await call_next(request)

        response = Response(status_code=429) if not allowed else await call_next(request)

        # Always attach rate limit headers
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Reset"] = str(reset_in)

        if not allowed:
            raise RateLimitExceededError(
                f"Rate limit exceeded. Try again in {reset_in} seconds."
            )

        return response

    async def _check_rate_limit(
        self, redis, ip: str, path: str, limit: int
    ) -> tuple[bool, int, int]:
        """
        Sliding window counter using Redis.
        Returns (allowed, remaining, reset_in_seconds).
        """
        key = RedisKeys.rate_limit(f"{ip}:{path}")
        window = 60  # 1-minute window
        now = int(time.time())
        window_start = now - window

        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)   # Remove old entries
        pipe.zadd(key, {str(now): now})                # Add current request
        pipe.zcard(key)                                # Count in window
        pipe.expire(key, window)                       # Auto-expire key
        results = await pipe.execute()

        count = results[2]
        remaining = max(0, limit - count)
        reset_in = window

        return count <= limit, remaining, reset_in

    @staticmethod
    def _get_ip(request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
