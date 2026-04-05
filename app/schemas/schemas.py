"""
Pydantic v2 schemas — request bodies, response models, and internal data shapes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


# ─────────────────────────────────────────
# Common
# ─────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None


# ─────────────────────────────────────────
# Auth — signup / login
# ─────────────────────────────────────────

class SignupRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=128)]
    name: Annotated[str, Field(min_length=1, max_length=100)]
    tenant_name: Annotated[str, Field(min_length=2, max_length=80)]
    join_existing_workspace: bool = False

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SignupResponse(BaseModel):
    user_id: str
    email: EmailStr
    tenant_id: str
    tenant_slug: str
    requires_workspace_approval: bool = False
    message: str


class TokenPair(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class EmailVerifyRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


# ─────────────────────────────────────────
# Google OAuth
# ─────────────────────────────────────────

class GoogleCallbackRequest(BaseModel):
    code: str
    state: str | None = None


class GoogleUserInfo(BaseModel):
    sub: str
    email: str
    name: str
    picture: str | None = None
    email_verified: bool = False


# ─────────────────────────────────────────
# User
# ─────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    name: str
    tenant_id: str
    password_hash: str | None = None
    auth_provider: Literal["email", "google"] = "email"
    google_id: str | None = None
    is_email_verified: bool = False
    role: Literal["user", "admin"] = "user"
    workspace_access_status: Literal["pending", "approved"] = "pending"
    approved_by: str | None = None
    approved_at: str | None = None


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    avatar_url: str | None = None


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    auth_provider: str
    is_email_verified: bool
    is_active: bool
    workspace_access_status: str
    approved_by: str | None
    approved_at: str | None
    avatar_url: str | None
    tenant_id: str
    razorpay_customer_id: str | None
    created_at: str
    updated_at: str


# ─────────────────────────────────────────
# Profile
# ─────────────────────────────────────────

class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    avatar_url: str | None = None


# ─────────────────────────────────────────
# Tenant
# ─────────────────────────────────────────

class TenantCreate(BaseModel):
    name: Annotated[str, Field(min_length=2, max_length=80)]

    @property
    def slug(self) -> str:
        import re
        return re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    email_suffix: str | None = None
    is_active: bool
    created_at: str


class PendingWorkspaceUserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    auth_provider: str
    is_email_verified: bool
    workspace_access_status: str
    tenant_id: str
    created_at: str


# ─────────────────────────────────────────
# Team
# ─────────────────────────────────────────

class TeamCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    description: str | None = None


class TeamResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: str | None
    created_by: str
    is_active: bool
    created_at: str


class TeamMemberAdd(BaseModel):
    user_id: str
    role: Literal["member", "lead"] = "member"


# ─────────────────────────────────────────
# Plan / Subscription
# ─────────────────────────────────────────

PlanName = Literal["tier_1", "tier_2", "tier_3"]


class PlanResponse(BaseModel):
    id: str
    name: str
    display_name: str
    plan_name: str
    price: str
    description: str
    button_text: str
    features: list[str]
    permissions: list[str]
    max_repos: int
    max_members: int
    is_popular: bool = False
    sort_order: int


class SubscriptionResponse(BaseModel):
    id: str
    tenant_id: str
    plan_id: str
    plan_code: str
    plan_name: str
    price: str
    description: str
    button_text: str
    features: list[str]
    permissions: list[str]
    max_repos: int
    max_members: int
    is_popular: bool = False
    status: str
    current_period_end: str | None


# ─────────────────────────────────────────
# S2S Token
# ─────────────────────────────────────────

class S2STokenRequest(BaseModel):
    service_name: Annotated[str, Field(min_length=1, max_length=80)]
    s2s_secret: str  # Pre-shared secret — validated server-side


class S2STokenResponse(BaseModel):
    token: str
    expires_in: int


# ─────────────────────────────────────────
# JWT internal payload (not exposed via API)
# ─────────────────────────────────────────

class JWTPayload(BaseModel):
    sub: str
    email: str
    name: str
    tenant_id: str
    team_id: str | None
    role: str
    plan: str
    customer_id: str | None
    permissions: list[str]
    token_version: int
    iat: int
    exp: int
    iss: str
    aud: str
    jti: str  # unique token id — used for blacklisting
