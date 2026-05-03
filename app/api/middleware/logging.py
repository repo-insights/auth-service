"""
app/api/middleware/logging.py
──────────────────────────────
Structured request/response logging middleware.
Logs method, path, status code, and duration for every request.
Attaches a correlation ID to each request context for log tracing.
"""

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

import structlog

from app.core.logging import get_logger

logger = get_logger(__name__)

# Headers that should never appear in logs
_SENSITIVE_HEADERS = {"authorization", "cookie", "x-api-key"}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate a correlation ID for distributed tracing
        correlation_id = str(uuid.uuid4())

        # Bind correlation ID to structlog context (visible in all log lines)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
        )

        start = time.perf_counter()

        # Log incoming request (skip health-check noise)
        if request.url.path not in ("/health", "/metrics"):
            logger.debug(
                "Request received",
                query_params=str(request.query_params),
                client_ip=request.client.host if request.client else "unknown",
            )

        response: Response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000

        if request.url.path not in ("/health", "/metrics"):
            log_fn = logger.warning if response.status_code >= 500 else logger.info
            log_fn(
                "Request completed",
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )

        # Propagate correlation ID to response headers for client-side tracing
        response.headers["X-Correlation-ID"] = correlation_id

        return response
