"""Auth endpoints — signup, login, Google SSO, token refresh, logout."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response, status
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.dependencies import get_current_active_user, rate_limit
from app.schemas.schemas import (
    EmailVerifyRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    ResendVerificationRequest,
    S2STokenRequest,
    S2STokenResponse,
    SignupRequest,
    SignupResponse,
    TokenPair,
)
from app.services import auth_service
from app.core.security import create_s2s_token

router = APIRouter(prefix="/auth", tags=["Auth"])

# Rate-limit dependencies
_login_limit = rate_limit("login", max_requests=5, window_seconds=60)
_signup_limit = rate_limit("signup", max_requests=3, window_seconds=60)


# ─────────────────────────────────────────
# Signup
# ─────────────────────────────────────────

@router.post(
    "/signup",
    status_code=status.HTTP_201_CREATED,
    response_model=SignupResponse,
    dependencies=[Depends(_signup_limit)],
)
async def signup(data: SignupRequest, request: Request) -> SignupResponse:
    return await auth_service.signup(data, request)


# ─────────────────────────────────────────
# Email verification
# ─────────────────────────────────────────

@router.post("/verify-email")
async def verify_email(body: EmailVerifyRequest) -> MessageResponse:
    result = await auth_service.verify_email(body.token)
    return MessageResponse(**result)


@router.post("/resend-verification")
async def resend_verification(body: ResendVerificationRequest) -> MessageResponse:
    result = await auth_service.resend_verification(body.email)
    return MessageResponse(**result)


# ─────────────────────────────────────────
# Email/password login
# ─────────────────────────────────────────

@router.post("/login/{tenant_slug}", dependencies=[Depends(_login_limit)])
async def login(
    tenant_slug: str,
    data: LoginRequest,
    request: Request,
    response: Response,
) -> TokenPair:
    token_pair, raw_refresh = await auth_service.login(data, tenant_slug, request)
    _set_refresh_cookie(response, raw_refresh)
    return token_pair


# ─────────────────────────────────────────
# Google OAuth
# ─────────────────────────────────────────

@router.get("/google")
async def google_login() -> RedirectResponse:
    url = auth_service.build_google_url()
    return RedirectResponse(url)


@router.get("/google/callback")
async def google_callback(code: str, request: Request, response: Response) -> TokenPair:
    token_pair, raw_refresh = await auth_service.handle_google_callback(code, request)
    _set_refresh_cookie(response, raw_refresh)
    return token_pair


# ─────────────────────────────────────────
# Token refresh
# ─────────────────────────────────────────

@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    refresh_token_cookie: Annotated[str | None, Cookie(alias="refresh_token")] = None,
    body: RefreshRequest | None = None,
) -> TokenPair:
    raw_refresh = refresh_token_cookie or (body.refresh_token if body else None)
    if not raw_refresh:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="No refresh token provided")

    token_pair, new_raw = await auth_service.refresh_tokens(raw_refresh, request)
    _set_refresh_cookie(response, new_raw)
    return token_pair


# ─────────────────────────────────────────
# Logout
# ─────────────────────────────────────────

@router.post("/logout")
async def logout(
    response: Response,
    current_user: dict = Depends(get_current_active_user),
    refresh_token_cookie: Annotated[str | None, Cookie(alias="refresh_token")] = None,
    body: RefreshRequest | None = None,
) -> MessageResponse:
    raw_refresh = refresh_token_cookie or (body.refresh_token if body else "")
    jwt_payload = current_user["_jwt"]
    jti = jwt_payload.get("jti", "")
    exp = jwt_payload.get("exp", 0)
    ttl = max(0, int(exp - time.time()))

    result = await auth_service.logout(raw_refresh, jti, ttl)
    _clear_refresh_cookie(response)
    return MessageResponse(**result)


@router.post("/logout-all")
async def logout_all(
    response: Response,
    current_user: dict = Depends(get_current_active_user),
) -> MessageResponse:
    result = await auth_service.logout_all(current_user["id"])
    _clear_refresh_cookie(response)
    return MessageResponse(**result)


# ─────────────────────────────────────────
# S2S Token
# ─────────────────────────────────────────

@router.post("/s2s/token")
async def issue_s2s_token(body: S2STokenRequest) -> S2STokenResponse:
    if body.s2s_secret != settings.s2s_secret_key:
        from fastapi import HTTPException
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid S2S secret")
    token, expires_in = create_s2s_token(body.service_name)
    return S2STokenResponse(token=token, expires_in=expires_in)


# ─────────────────────────────────────────
# Cookie helpers (httpOnly, Secure, SameSite=Lax)
# ─────────────────────────────────────────

def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    max_age = settings.jwt_refresh_token_expire_hours * 3600
    response.set_cookie(
        key="refresh_token",
        value=raw_token,
        httponly=True,
        secure=settings.app_env != "development",
        samesite="lax",
        max_age=max_age,
        path="/api/v1/auth/refresh",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key="refresh_token", path="/api/v1/auth/refresh")
