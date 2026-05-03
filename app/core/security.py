"""
app/core/security.py
─────────────────────
JWT creation/verification (RSA asymmetric) and password hashing utilities.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.exceptions import InvalidTokenError, TokenExpiredError

# ── Password hashing ──────────────────────────────────────────────────────────
# Argon2 is the primary hasher; bcrypt is the fallback for migration support.
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated="auto",
    argon2__memory_cost=65536,   # 64 MB
    argon2__time_cost=3,
    argon2__parallelism=4,
)


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password using Argon2."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a stored hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ── JWT helpers ───────────────────────────────────────────────────────────────

TokenPayload = Dict[str, Any]


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def create_access_token(
    *,
    user_id: UUID,
    role: str,
    scopes: List[str],
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Create a signed JWT access token.

    Payload structure:
        sub   – user UUID (string)
        role  – user role string
        scopes – list of permission strings
        type  – "access"
        iat   – issued-at timestamp
        exp   – expiry timestamp
    """
    now = _utcnow()
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: TokenPayload = {
        "sub": str(user_id),
        "role": role,
        "scopes": scopes,
        "type": "access",
        "iat": now,
        "exp": expire,
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(
        payload,
        settings.jwt_private_key,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(*, user_id: UUID, session_id: str) -> str:
    """
    Create a signed JWT refresh token.

    The session_id ties this token to a specific DB row so it can be
    invalidated without affecting other sessions (multi-device support).
    """
    now = _utcnow()
    expire = now + timedelta(hours=settings.REFRESH_TOKEN_EXPIRE_HOURS)

    payload: TokenPayload = {
        "sub": str(user_id),
        "session_id": session_id,
        "type": "refresh",
        "iat": now,
        "exp": expire,
    }

    return jwt.encode(
        payload,
        settings.jwt_private_key,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str) -> TokenPayload:
    """
    Decode and validate a JWT token.

    Raises:
        TokenExpiredError: if the token has expired.
        InvalidTokenError: for any other verification failure.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_public_key,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError as exc:
        if "expired" in str(exc).lower():
            raise TokenExpiredError("Token has expired") from exc
        raise InvalidTokenError(f"Token validation failed: {exc}") from exc


def decode_access_token(token: str) -> TokenPayload:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise InvalidTokenError("Expected an access token")
    return payload


def decode_refresh_token(token: str) -> TokenPayload:
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise InvalidTokenError("Expected a refresh token")
    return payload
