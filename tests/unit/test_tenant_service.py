"""Unit tests for workspace-domain helper rules."""

from __future__ import annotations

from app.services import tenant_service


def test_workspace_email_suffix_uses_corporate_domain() -> None:
    assert tenant_service.get_workspace_email_suffix("alice@wipro.com") == "wipro.com"


def test_workspace_email_suffix_ignores_public_domain() -> None:
    assert tenant_service.get_workspace_email_suffix("ramesh@gmail.com") is None


def test_can_join_workspace_requires_matching_suffix() -> None:
    tenant = {"email_suffix": "wipro.com"}
    assert tenant_service.can_join_workspace(tenant, "abc@wipro.com") is True
    assert tenant_service.can_join_workspace(tenant, "abc@gmail.com") is False
