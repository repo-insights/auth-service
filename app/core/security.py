"""
Security module — password hashing, JWT issuance/validation, token helpers.
Never import from routes directly; always inject via FastAPI dependencies.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.schemas.schemas import JWTPayload

# ─────────────────────────────────────────
# Password hashing
# ─────────────────────────────────────────

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ─────────────────────────────────────────
# Token hashing (for DB storage — never store raw tokens)
# ─────────────────────────────────────────

def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def generate_opaque_token(nbytes: int = 48) -> str:
    """URL-safe random token (e.g. for refresh & email-verification tokens)."""
    return secrets.token_urlsafe(nbytes)


# ─────────────────────────────────────────
# JWT — Access token
# ─────────────────────────────────────────

def create_access_token(
    user_id: str,
    email: str,
    name: str,
    tenant_id: str,
    team_id: str | None,
    role: str,
    plan: str,
    customer_id: str | None,
    permissions: list[str],
    token_version: int,
) -> tuple[str, JWTPayload]:
    """
    Mint a signed JWT. Returns (raw_token, decoded_payload).
    The decoded payload can be cached / used for immediate response.
    """
    now = int(datetime.now(timezone.utc).timestamp())
    expire = now + settings.jwt_access_token_expire_minutes * 60
    jti = str(uuid.uuid4())

    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "tenant_id": tenant_id,
        "team_id": team_id,
        "role": role,
        "plan": plan,
        "customer_id": customer_id,
        "permissions": permissions,
        "token_version": token_version,
        "iat": now,
        "exp": expire,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": jti,
    }

    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    parsed = JWTPayload(**payload)
    return token, parsed


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT.
    Raises jose.JWTError on any validation failure.
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )


# ─────────────────────────────────────────
# Refresh token
# ─────────────────────────────────────────

def create_refresh_token() -> tuple[str, str]:
    """
    Returns (raw_token, token_hash).
    Store only the hash in DB/Redis; send the raw token to the client.
    """
    raw = generate_opaque_token(64)
    return raw, sha256_hex(raw)


# ─────────────────────────────────────────
# S2S token
# ─────────────────────────────────────────

def create_s2s_token(service_name: str) -> tuple[str, int]:
    """
    Mint a service-to-service JWT.
    Returns (raw_token, expires_in_seconds).
    """
    now = int(datetime.now(timezone.utc).timestamp())
    expire = now + settings.s2s_token_expire_minutes * 60

    payload = {
        "service_name": service_name,
        "issued_at": now,
        "expiry": expire,
        "issuer": settings.jwt_issuer,
        "iat": now,
        "exp": expire,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": str(uuid.uuid4()),
    }

    token = jwt.encode(payload, settings.s2s_secret_key, algorithm=settings.jwt_algorithm)
    return token, settings.s2s_token_expire_minutes * 60


def decode_s2s_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.s2s_secret_key,
        algorithms=[settings.jwt_algorithm],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )


# ─────────────────────────────────────────
# Email-verification token
# ─────────────────────────────────────────

def create_email_verification_token() -> tuple[str, str]:
    """Returns (raw_token, sha256_hash)."""
    raw = generate_opaque_token(32)
    return raw, sha256_hex(raw)
