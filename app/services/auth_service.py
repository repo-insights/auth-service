"""
Auth service — orchestrates signup, login, token refresh, and Google SSO.
Keeps all business logic out of route handlers.
"""

from __future__ import annotations

import json
import logging
import secrets
from typing import Any

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_email_verification_token,
    create_refresh_token,
    verify_password,
)
from app.schemas.schemas import (
    PLAN_PERMISSIONS,
    LoginRequest,
    SignupRequest,
    SignupResponse,
    TokenPair,
)
from app.services import (
    auth_state_service,
    email_service,
    google_oauth_service,
    tenant_service,
    token_service,
    user_service,
)
from app.schemas.schemas import UserCreate

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

async def _build_token_pair(user: dict, request: Request) -> tuple[TokenPair, str]:
    """
    Builds access + refresh tokens for a user.
    Also fetches the active subscription so permissions are always fresh.
    """
    sub = await tenant_service.get_active_subscription(user["tenant_id"])
    plan_name = sub["plan_name"] if sub else "tier_1"
    permissions = json.loads(sub["plan_permissions"]) if sub else PLAN_PERMISSIONS["tier_1"]

    # Primary team (first team membership, if any)
    from app.db.database import fetch_one
    team_row = await fetch_one(
        "SELECT team_id FROM user_teams WHERE user_id = ? LIMIT 1",
        [user["id"]],
    )
    team_id = team_row["team_id"] if team_row else None

    access_token, _ = create_access_token(
        user_id=user["id"],
        email=user["email"],
        name=user["name"],
        tenant_id=user["tenant_id"],
        team_id=team_id,
        role=user["role"],
        plan=plan_name,
        customer_id=user.get("razorpay_customer_id"),
        permissions=permissions,
        token_version=user["token_version"],
    )

    raw_refresh, _ = create_refresh_token()
    await token_service.store_refresh_token(
        raw_token=raw_refresh,
        user_id=user["id"],
        token_version=user["token_version"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    token_pair = TokenPair(
        access_token=access_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )
    return token_pair, raw_refresh


# ─────────────────────────────────────────
# Email/password signup
# ─────────────────────────────────────────

async def signup(data: SignupRequest, request: Request) -> SignupResponse:
    existing = await user_service.get_user_by_email_global(data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    workspace = await tenant_service.get_tenant_by_name(data.tenant_name)
    requires_workspace_approval = False
    user_role = "user"
    workspace_access_status = "pending"
    approved_by = None
    approved_at = None

    if workspace:
        if not tenant_service.can_join_workspace(workspace, data.email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": (
                        "Workspace name already exists and your email domain does not match "
                        "that workspace. Please use an individual workspace or choose a unique workspace name."
                    ),
                    "workspace_exists": True,
                    "can_join_workspace": False,
                    "tenant_slug": workspace["slug"],
                },
            )
        if not data.join_existing_workspace:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Workspace name already exists. Do you want to be a part of that workspace?",
                    "workspace_exists": True,
                    "can_join_workspace": True,
                    "tenant_slug": workspace["slug"],
                },
            )
        tenant = workspace
        requires_workspace_approval = True
    else:
        tenant = await tenant_service.create_tenant(
            data.tenant_name,
            email_suffix=tenant_service.get_workspace_email_suffix(data.email),
        )
        await tenant_service.create_default_subscription(tenant["id"])
        user_role = "admin"
        workspace_access_status = "approved"

    from app.core.security import hash_password
    user = await user_service.create_user(
        UserCreate(
            email=data.email,
            name=data.name,
            tenant_id=tenant["id"],
            password_hash=hash_password(data.password),
            auth_provider="email",
            is_email_verified=False,
            role=user_role,
            workspace_access_status=workspace_access_status,
            approved_by=approved_by,
            approved_at=approved_at,
        )
    )

    # Send verification email
    raw_token, _ = create_email_verification_token()
    await token_service.store_email_verification_token(raw_token, user["id"])
    await email_service.send_verification_email(user["email"], user["name"], raw_token)

    return SignupResponse(
        user_id=user["id"],
        email=user["email"],
        tenant_id=tenant["id"],
        tenant_slug=tenant["slug"],
        requires_workspace_approval=requires_workspace_approval,
        message=(
            "Account created. Please verify your email, then wait for the workspace admin to approve your access."
            if requires_workspace_approval
            else "Account created — please verify your email before logging in"
        ),
    )


# ─────────────────────────────────────────
# Email verification
# ─────────────────────────────────────────

async def verify_email(raw_token: str) -> dict[str, str]:
    row = await token_service.validate_email_verification_token(raw_token)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )
    await user_service.mark_email_verified(row["user_id"])
    user = await user_service.get_user_by_id(row["user_id"])
    if user and user["workspace_access_status"] != "approved":
        return {"message": "Email verified successfully — please wait for the workspace admin to approve your access"}
    return {"message": "Email verified successfully — you can now log in"}


async def resend_verification(email: str) -> dict[str, str]:
    # We don't know tenant_id here — look up by email globally (best-effort)
    from app.db.database import fetch_one
    user = await fetch_one(
        "SELECT * FROM users WHERE email = ? AND deleted_at IS NULL AND is_email_verified = 0 LIMIT 1",
        [email.strip().lower()],
    )
    # Always return same message to avoid email enumeration
    if user:
        raw_token, _ = create_email_verification_token()
        await token_service.store_email_verification_token(raw_token, user["id"])
        await email_service.send_verification_email(user["email"], user["name"], raw_token)
    return {"message": "If that email is registered and unverified, a new link has been sent"}


# ─────────────────────────────────────────
# Email/password login
# ─────────────────────────────────────────

async def login(data: LoginRequest, tenant_slug: str, request: Request) -> tuple[TokenPair, str]:
    tenant = await tenant_service.get_tenant_by_slug(tenant_slug)
    if not tenant or not tenant["is_active"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    user = await user_service.get_user_by_email(data.email, tenant["id"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user["password_hash"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account uses Google Sign-In — please use that instead",
        )

    if not verify_password(data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user["is_email_verified"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in",
        )

    if user["workspace_access_status"] != "approved":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your workspace access is pending admin approval",
        )

    if not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account suspended")

    return await _build_token_pair(user, request)


# ─────────────────────────────────────────
# Google OAuth
# ─────────────────────────────────────────

def build_google_url() -> str:
    state = secrets.token_urlsafe(16)
    return google_oauth_service.build_google_auth_url(state)


async def handle_google_callback(code: str, request: Request) -> tuple[TokenPair, str]:
    try:
        tokens = await google_oauth_service.exchange_code_for_tokens(code)
        g_user = await google_oauth_service.get_google_user_info(tokens["access_token"])
    except Exception as exc:
        logger.error("Google OAuth error: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Google OAuth failed")

    # Check if user exists (by google_id)
    user = await user_service.get_user_by_google_id(g_user.sub)

    if not user:
        existing_email_user = await user_service.get_user_by_email_global(g_user.email)
        if existing_email_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            )

        # New user — auto-create tenant named after their email domain
        domain = g_user.email.split("@")[-1]
        tenant = await tenant_service.create_tenant(
            domain,
            email_suffix=tenant_service.get_workspace_email_suffix(g_user.email),
        )
        await tenant_service.create_default_subscription(tenant["id"])

        user = await user_service.create_user(
            UserCreate(
                email=g_user.email,
                name=g_user.name,
                tenant_id=tenant["id"],
                auth_provider="google",
                google_id=g_user.sub,
                is_email_verified=True,  # Google verifies email
                role="admin",
                workspace_access_status="approved",
            )
        )

    if not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account suspended")

    return await _build_token_pair(user, request)


# ─────────────────────────────────────────
# Token refresh
# ─────────────────────────────────────────

async def refresh_tokens(raw_refresh: str, request: Request) -> tuple[TokenPair, str]:
    row = await token_service.validate_refresh_token(raw_refresh)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Rotate: revoke old, issue new
    from app.core.security import sha256_hex
    await token_service.revoke_refresh_token_by_hash(sha256_hex(raw_refresh))

    user = await user_service.get_user_by_id(row["user_id"])
    if not user or not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return await _build_token_pair(user, request)


# ─────────────────────────────────────────
# Logout
# ─────────────────────────────────────────

async def logout(raw_refresh: str, access_jti: str, access_ttl_remaining: int) -> dict[str, str]:
    from app.core.security import sha256_hex
    await token_service.revoke_refresh_token_by_hash(sha256_hex(raw_refresh))
    if access_jti:
        await auth_state_service.blacklist_access_token(access_jti, access_ttl_remaining)
    return {"message": "Logged out successfully"}


async def logout_all(user_id: str) -> dict[str, str]:
    """Invalidate ALL sessions for the user by bumping token_version."""
    await user_service.increment_token_version(user_id)
    await token_service.revoke_all_refresh_tokens_for_user(user_id)
    return {"message": "All sessions invalidated"}
