"""Unit tests for Turso TLS configuration helpers."""

from __future__ import annotations

import os

import pytest

from app.db import database


def test_validate_db_tls_config_allows_default_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(database.settings, "turso_database_tls", True)
    monkeypatch.setattr(database.settings, "turso_database_url", "libsql://example.turso.io")

    database._validate_db_tls_config()


def test_validate_db_tls_config_rejects_libsql_without_port_when_tls_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(database.settings, "turso_database_tls", False)
    monkeypatch.setattr(database.settings, "turso_database_url", "libsql://example.turso.io")

    with pytest.raises(RuntimeError, match="requires an explicit port"):
        database._validate_db_tls_config()


def test_configure_db_ssl_prefers_custom_cert_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(database.settings, "turso_ssl_cert_file", "/tmp/local-ca.pem")
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)

    database._configure_db_ssl()

    assert os.environ["SSL_CERT_FILE"] == "/tmp/local-ca.pem"
