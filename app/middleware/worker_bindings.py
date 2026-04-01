"""Middleware that exposes Cloudflare Worker bindings to the DB layer."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.db.database import reset_d1_binding, set_d1_binding


class WorkerBindingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        env = request.scope.get("env")
        binding = getattr(env, settings.d1_binding_name, None) if env is not None else None
        token = set_d1_binding(binding)
        try:
            return await call_next(request)
        finally:
            reset_d1_binding(token)
