"""
FastAPI dependency-injection layer.
All route handlers should depend on functions here, not call services directly.
"""

from __future__ import annotations

import logging

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from jose import JWTError

from app.core.security import decode_access_token
from app.services import auth_state_service, user_service

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# Bearer token extraction
# ─────────────────────────────────────────

async def get_token_from_header(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization.removeprefix("Bearer ").strip()


# ─────────────────────────────────────────
# Current user
# ─────────────────────────────────────────

async def get_current_user(token: str = Depends(get_token_from_header)) -> dict:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
    except JWTError as exc:
        logger.debug("JWT decode error: %s", exc)
        raise credentials_exc from exc

    jti: str | None = payload.get("jti")
    if jti and await auth_state_service.is_access_token_blacklisted(jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise credentials_exc

    # Validate token_version (allows forced global logout)
    db_user = await user_service.get_user_by_id(user_id)
    if not db_user:
        raise credentials_exc
    if not db_user["is_active"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account suspended")
    if db_user["token_version"] != payload.get("token_version"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalidated — please log in again",
        )

    return {**db_user, "_jwt": payload}


async def get_current_active_user(current_user: dict = Depends(get_current_user)) -> dict:
    if not current_user.get("is_active"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")
    return current_user


async def require_admin(current_user: dict = Depends(get_current_active_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


# ─────────────────────────────────────────
# Tenant isolation guard
# ─────────────────────────────────────────

def assert_same_tenant(current_user: dict, target_tenant_id: str) -> None:
    """Raise 403 if the current user doesn't belong to the requested tenant."""
    if current_user["tenant_id"] != target_tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access denied")


# ─────────────────────────────────────────
# Rate-limit dependency factory
# ─────────────────────────────────────────

def rate_limit(prefix: str, max_requests: int, window_seconds: int):
    """Returns a FastAPI dependency that enforces a per-IP sliding-window limit."""

    async def _dep(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        allowed = await auth_state_service.check_rate_limit(prefix, ip, max_requests, window_seconds)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests — max {max_requests} per {window_seconds}s",
                headers={"Retry-After": str(window_seconds)},
            )

    return _dep
