"""Unit tests for Pydantic schemas — validation rules."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.schemas import PLAN_PERMISSIONS, SignupRequest, TeamCreate, TeamMemberAdd


def test_signup_requires_uppercase():
    with pytest.raises(ValidationError, match="uppercase"):
        SignupRequest(
            email="a@b.com", password="alllower1", name="Alice", tenant_name="Acme"
        )


def test_signup_requires_digit():
    with pytest.raises(ValidationError, match="digit"):
        SignupRequest(
            email="a@b.com", password="NoDigitsHere", name="Alice", tenant_name="Acme"
        )


def test_signup_password_too_short():
    with pytest.raises(ValidationError):
        SignupRequest(
            email="a@b.com", password="Ab1!", name="Alice", tenant_name="Acme"
        )


def test_valid_signup():
    req = SignupRequest(
        email="alice@acme.com",
        password="SecurePass1",
        name="Alice",
        tenant_name="Acme Corp",
    )
    assert req.email == "alice@acme.com"
    assert req.join_existing_workspace is False


def test_plan_permissions_map_is_ordered():
    assert "read_repo" in PLAN_PERMISSIONS["tier_1"]
    assert "ask_ai" in PLAN_PERMISSIONS["tier_2"]
    assert "multi_repo" in PLAN_PERMISSIONS["tier_3"]
    # Lower tiers are subsets
    for perm in PLAN_PERMISSIONS["tier_1"]:
        assert perm in PLAN_PERMISSIONS["tier_2"]
    for perm in PLAN_PERMISSIONS["tier_2"]:
        assert perm in PLAN_PERMISSIONS["tier_3"]


def test_team_member_role_default():
    m = TeamMemberAdd(user_id="u1")
    assert m.role == "member"


def test_team_member_invalid_role():
    with pytest.raises(ValidationError):
        TeamMemberAdd(user_id="u1", role="superadmin")
