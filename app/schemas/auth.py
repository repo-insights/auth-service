"""
app/schemas/auth.py
────────────────────
Pydantic request / response schemas for auth endpoints.
"""

import re
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Shared validators ──────────────────────────────────────────────────────────

PASSWORD_REGEX = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,128}$"
)


def validate_password_strength(v: str) -> str:
    if not PASSWORD_REGEX.match(v):
        raise ValueError(
            "Password must be 8–128 characters and include uppercase, "
            "lowercase, digit, and special character (@$!%*?&)"
        )
    return v


# ── Request schemas ────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class GoogleAuthRequest(BaseModel):
    """Receives the ID token from the client after Google's OAuth redirect."""
    id_token: str = Field(..., description="Google ID token from the client SDK")


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Opaque refresh token string")


class LogoutRequest(BaseModel):
    refresh_token: str = Field(..., description="Refresh token to invalidate")


# ── Response schemas ───────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = Field(description="Access token TTL in seconds")


class UserResponse(BaseModel):
    """Public-safe user representation — no password hash exposed."""
    id: UUID
    email: str
    role: str
    scopes: List[str]
    subscription_type: str
    is_verified: bool
    is_active: bool

    model_config = {"from_attributes": True}


class SignupResponse(BaseModel):
    message: str = "Account created. Please verify your email."
    user: UserResponse


class MessageResponse(BaseModel):
    message: str
