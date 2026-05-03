"""
app/services/auth_service.py
─────────────────────────────
Business logic for all authentication flows.

Coordinates:
  • UserRepository     – user CRUD
  • TokenRepository    – refresh token lifecycle
  • SecurityService    – password + JWT utilities
  • GoogleOAuthService – ID token verification
"""

from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AccountLockedError,
    EmailAlreadyExistsError,
    GoogleAuthError,
    InvalidCredentialsError,
    RefreshTokenRevokedError,
    UserNotFoundError,
)
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.token_repository import TokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenResponse
from app.services.google_oauth_service import GoogleOAuthService

logger = get_logger(__name__)


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._user_repo = UserRepository(session)
        self._token_repo = TokenRepository(session)
        self._google_service = GoogleOAuthService()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_token_response(self, user: User, session_id: str) -> TokenResponse:
        """Create access + refresh tokens and wrap in a TokenResponse."""
        from app.core.config import settings  # avoid circular at module level

        access_token = create_access_token(
            user_id=user.id,
            role=user.role,
            scopes=user.scopes,
        )
        refresh_token = create_refresh_token(
            user_id=user.id,
            session_id=session_id,
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def _issue_tokens(
        self,
        user: User,
        *,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenResponse:
        """Persist a new refresh token and return the token pair."""
        # We first create the DB row to get session_id (row UUID).
        # Then we embed that session_id in the JWT.
        # The raw refresh JWT is what the client receives.
        import uuid

        session_id = str(uuid.uuid4())

        access_token = create_access_token(
            user_id=user.id,
            role=user.role,
            scopes=user.scopes,
        )
        raw_refresh = create_refresh_token(
            user_id=user.id,
            session_id=session_id,
        )

        await self._token_repo.create(
            user_id=user.id,
            raw_token=raw_refresh,
            device_info=device_info,
            ip_address=ip_address,
        )

        from app.core.config import settings

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    # ── Signup ────────────────────────────────────────────────────────────────

    async def signup(
        self,
        *,
        email: str,
        password: str,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Tuple[User, TokenResponse]:
        existing = await self._user_repo.get_by_email(email)
        if existing:
            raise EmailAlreadyExistsError()

        user = await self._user_repo.create(
            email=email,
            hashed_password=hash_password(password),
            is_verified=False,
            role="user",
            scopes=["read:own"],
        )

        tokens = await self._issue_tokens(
            user, device_info=device_info, ip_address=ip_address
        )
        logger.info("User signed up", user_id=str(user.id), email=email)
        return user, tokens

    # ── Email / Password Login ────────────────────────────────────────────────

    async def login(
        self,
        *,
        email: str,
        password: str,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenResponse:
        user = await self._user_repo.get_by_email(email)

        if not user:
            # Timing-safe: still hash to avoid user enumeration
            hash_password("timing_safe_dummy")
            raise InvalidCredentialsError()

        if user.is_locked:
            raise AccountLockedError()

        if not user.hashed_password or not verify_password(password, user.hashed_password):
            await self._user_repo.increment_failed_login(user)
            logger.warning(
                "Failed login attempt",
                email=email,
                attempts=user.failed_login_attempts,
            )
            if user.is_locked:
                raise AccountLockedError()
            raise InvalidCredentialsError()

        # Successful login — reset failure counter
        await self._user_repo.reset_failed_login(user)

        tokens = await self._issue_tokens(
            user, device_info=device_info, ip_address=ip_address
        )
        logger.info("User logged in", user_id=str(user.id))
        return tokens

    # ── Google OAuth ──────────────────────────────────────────────────────────

    async def google_login(
        self,
        *,
        id_token: str,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenResponse:
        try:
            google_user = await self._google_service.verify_id_token(id_token)
        except Exception as exc:
            logger.warning("Google token verification failed", error=str(exc))
            raise GoogleAuthError("Invalid Google ID token") from exc

        google_id = google_user["sub"]
        email = google_user["email"]

        # Try to find by Google ID first, then by email (account linking)
        user = await self._user_repo.get_by_google_id(google_id)
        if not user:
            user = await self._user_repo.get_by_email(email)

        if not user:
            # First time Google login — create account (pre-verified)
            user = await self._user_repo.create(
                email=email,
                google_id=google_id,
                is_verified=True,  # Google guarantees email ownership
                role="user",
                scopes=["read:own"],
            )
            logger.info("Google user created", user_id=str(user.id), email=email)
        elif not user.google_id:
            # Existing email account — link Google ID
            user.google_id = google_id
            user.is_verified = True

        tokens = await self._issue_tokens(
            user, device_info=device_info, ip_address=ip_address
        )
        logger.info("Google login success", user_id=str(user.id))
        return tokens

    # ── Refresh ───────────────────────────────────────────────────────────────

    async def refresh_tokens(
        self,
        *,
        raw_refresh_token: str,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenResponse:
        # 1. Verify JWT signature & expiry
        payload = decode_refresh_token(raw_refresh_token)
        user_id = UUID(payload["sub"])

        # 2. Validate against DB (not revoked, not expired)
        stored = await self._token_repo.get_by_raw_token(raw_refresh_token)
        if not stored:
            # Token reuse detected — revoke all sessions for safety
            await self._token_repo.revoke_all_for_user(user_id)
            logger.warning(
                "Refresh token reuse detected — all sessions revoked",
                user_id=str(user_id),
            )
            raise RefreshTokenRevokedError()

        # 3. Load user
        user = await self._user_repo.get_by_id(user_id)
        if not user or not user.is_active:
            await self._token_repo.revoke(stored)
            raise UserNotFoundError()

        # 4. Rotation: invalidate old token
        await self._token_repo.revoke(stored)

        # 5. Issue new token pair
        tokens = await self._issue_tokens(
            user, device_info=device_info, ip_address=ip_address
        )
        logger.info("Tokens refreshed", user_id=str(user.id))
        return tokens

    # ── Logout ────────────────────────────────────────────────────────────────

    async def logout(self, *, raw_refresh_token: str) -> None:
        stored = await self._token_repo.get_by_raw_token(raw_refresh_token)
        if stored:
            await self._token_repo.revoke(stored)
            logger.info("User logged out", token_id=str(stored.id))

    async def logout_all_devices(self, *, user_id: UUID) -> None:
        await self._token_repo.revoke_all_for_user(user_id)
        logger.info("All sessions revoked", user_id=str(user_id))
