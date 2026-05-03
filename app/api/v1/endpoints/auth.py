"""
app/api/v1/endpoints/auth.py
─────────────────────────────
Auth endpoints:
  POST /auth/signup
  POST /auth/login
  POST /auth/google
  POST /auth/refresh
  POST /auth/logout
"""

from fastapi import APIRouter, Depends, Request, status

from app.api.dependencies import (
    get_auth_service,
    get_client_ip,
    get_current_user,
    get_device_info,
)
from app.core.logging import get_logger
from app.models.user import User
from app.schemas.auth import (
    GoogleAuthRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshTokenRequest,
    SignupRequest,
    SignupResponse,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import AuthService

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def signup(
    body: SignupRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    device_info: str | None = Depends(get_device_info),
) -> SignupResponse:
    """
    Create a new user with email + password.

    - Validates password strength
    - Hashes password with Argon2
    - Issues access + refresh token pair
    """
    ip = get_client_ip(request)
    user, tokens = await auth_service.signup(
        email=body.email,
        password=body.password,
        device_info=device_info,
        ip_address=ip,
    )
    return SignupResponse(
        message="Account created successfully. Please verify your email.",
        user=UserResponse.model_validate(user),
        # Embed tokens in the response body so the client can store them
        # In production you may prefer HttpOnly cookies instead
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with email and password",
)
async def login(
    body: LoginRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    device_info: str | None = Depends(get_device_info),
) -> TokenResponse:
    """
    Authenticate with email + password.

    - Checks account lock status
    - Verifies password hash
    - Returns access + refresh token pair
    - Tracks failed attempts; locks account after threshold
    """
    ip = get_client_ip(request)
    return await auth_service.login(
        email=body.email,
        password=body.password,
        device_info=device_info,
        ip_address=ip,
    )


@router.post(
    "/google",
    response_model=TokenResponse,
    summary="Login or register via Google OAuth",
)
async def google_auth(
    body: GoogleAuthRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    device_info: str | None = Depends(get_device_info),
) -> TokenResponse:
    """
    Authenticate using a Google ID token.

    - Verifies the ID token with Google's public keys
    - Creates account if first login
    - Links Google identity to existing email account if present
    - Returns access + refresh token pair
    """
    ip = get_client_ip(request)
    return await auth_service.google_login(
        id_token=body.id_token,
        device_info=device_info,
        ip_address=ip,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token and issue new token pair",
)
async def refresh_tokens(
    body: RefreshTokenRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    device_info: str | None = Depends(get_device_info),
) -> TokenResponse:
    """
    Exchange a valid refresh token for a new access + refresh token pair.

    - Validates the refresh JWT
    - Checks DB to ensure token is not revoked/expired
    - Implements rotation: old token is immediately invalidated
    - Detects token reuse and revokes all sessions as a security measure
    """
    ip = get_client_ip(request)
    return await auth_service.refresh_tokens(
        raw_refresh_token=body.refresh_token,
        device_info=device_info,
        ip_address=ip,
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Invalidate the current session",
)
async def logout(
    body: LogoutRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    """
    Revoke the provided refresh token (single-device logout).
    The corresponding access token will naturally expire.
    """
    await auth_service.logout(raw_refresh_token=body.refresh_token)
    return MessageResponse(message="Logged out successfully")


@router.post(
    "/logout-all",
    response_model=MessageResponse,
    summary="Invalidate all sessions for the current user",
)
async def logout_all(
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    """
    Revoke ALL refresh tokens for the authenticated user (logout everywhere).
    Requires a valid access token.
    """
    await auth_service.logout_all_devices(user_id=current_user.id)
    return MessageResponse(message="All sessions terminated successfully")
