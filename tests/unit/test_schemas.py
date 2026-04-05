"""Unit tests for Pydantic schemas — validation rules."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.schemas import PlanResponse, SignupRequest, TeamCreate, TeamMemberAdd


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


def test_plan_response_supports_db_backed_metadata() -> None:
    plan = PlanResponse(
        id="plan_tier2",
        name="tier_2",
        display_name="Professional",
        plan_name="Professional",
        description="For growing teams that need AI and collaboration features.",
        button_text="Start free trial",
        features=["5 repositories", "5 members", "AI Q&A"],
        permissions=["read_repo", "ask_ai"],
        max_repos=5,
        max_members=5,
        is_popular=True,
        sort_order=2,
    )
    assert plan.plan_name == "Professional"
    assert "AI Q&A" in plan.features


def test_team_member_role_default():
    m = TeamMemberAdd(user_id="u1")
    assert m.role == "member"


def test_team_member_invalid_role():
    with pytest.raises(ValidationError):
        TeamMemberAdd(user_id="u1", role="superadmin")
