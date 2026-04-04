"""
Database layer — supports libsql and Cloudflare D1 binding backends.
Exposes a thin async-compatible interface: execute(), fetch_one(), fetch_all().
"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
import logging
import os
from typing import Any
from urllib.parse import urlparse

import certifi
try:
    import libsql
except ImportError:  # pragma: no cover - only relevant in Worker runtime packaging
    libsql = None

from app.core.config import settings

logger = logging.getLogger(__name__)

# Module-level connection — created once at startup
_conn: libsql.Connection | None = None
_d1_binding: ContextVar[Any | None] = ContextVar("d1_binding", default=None)
_init_lock = asyncio.Lock()


def _using_d1_binding_backend() -> bool:
    return settings.db_backend == "d1_binding"


def set_d1_binding(binding: Any | None) -> object:
    return _d1_binding.set(binding)


def reset_d1_binding(token: object) -> None:
    _d1_binding.reset(token)


def _get_d1_binding() -> Any:
    binding = _d1_binding.get()
    if binding is None:
        raise RuntimeError(
            "D1 binding is not available in the current request context. "
            "Configure WorkerBindingMiddleware and ensure the Worker exposes the configured binding."
        )
    return binding


def _configure_db_ssl() -> None:
    """Set the CA bundle used by Python before creating the client."""
    cert_file = settings.turso_ssl_cert_file or os.environ.get("SSL_CERT_FILE") or certifi.where()
    os.environ["SSL_CERT_FILE"] = cert_file
    logger.info("Using SSL certificate bundle for D1 client: %s", cert_file)


def _validate_db_tls_config() -> None:
    if settings.turso_database_tls:
        return

    parsed_url = urlparse(settings.turso_database_url)
    if parsed_url.scheme == "libsql" and parsed_url.port is None:
        raise RuntimeError(
            "TURSO_DATABASE_TLS=false requires an explicit port in TURSO_DATABASE_URL for libsql:// URLs. "
            "Hosted Turso endpoints normally require TLS, so prefer fixing the certificate chain or "
            "using TURSO_SSL_CERT_FILE instead."
        )


async def init_db() -> None:
    global _conn
    if _using_d1_binding_backend():
        logger.info("Database backend set to d1_binding; skipping libsql connection initialisation")
        return

    if _conn is not None:
        return

    async with _init_lock:
        if _conn is not None:
            return

        if libsql is None:
            raise RuntimeError("The libsql package is required when DB_BACKEND=libsql")

        _validate_db_tls_config()
        _configure_db_ssl()

        if not settings.turso_database_tls:
            logger.warning("D1 TLS verification is disabled. Use this only for local development.")

        # Lazily initialise the shared libsql client so serverless runtimes work
        # even when ASGI startup hooks are skipped on cold start.
        _conn = libsql.connect(
            database=settings.turso_database_url,
            auth_token=settings.turso_auth_token
        )
        logger.info("D1 database connection initialised")


async def close_db() -> None:
    global _conn
    if _using_d1_binding_backend():
        return

    if _conn:
        _conn.close()
        _conn = None
        logger.info("D1 database connection closed")


def get_client() -> Any:
    if _using_d1_binding_backend():
        raise RuntimeError("libsql client is unavailable when DB_BACKEND=d1_binding")
    if _conn is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    return _conn


def _bind_statement(statement: Any, args: list[Any]) -> Any:
    if not args:
        return statement
    return statement.bind(*args)


async def _d1_execute(sql: str, args: list[Any]) -> None:
    statement = _get_d1_binding().prepare(sql)
    await _bind_statement(statement, args).run()


async def _d1_fetch_one(sql: str, args: list[Any]) -> dict[str, Any] | None:
    statement = _get_d1_binding().prepare(sql)
    row = await _bind_statement(statement, args).first()
    return dict(row) if row else None


async def _d1_fetch_all(sql: str, args: list[Any]) -> list[dict[str, Any]]:
    statement = _get_d1_binding().prepare(sql)
    result = await _bind_statement(statement, args).run()
    rows = getattr(result, "results", None)
    if rows is None and isinstance(result, dict):
        rows = result.get("results", [])
    return [dict(row) for row in (rows or [])]


async def _d1_execute_batch(statements: list[tuple[str, list[Any]]]) -> None:
    binding = _get_d1_binding()
    prepared = [_bind_statement(binding.prepare(sql), args or []) for sql, args in statements]
    await binding.batch(prepared)


# ─────────────────────────────────────────
# Query helpers
# ─────────────────────────────────────────

async def execute(sql: str, args: list[Any] | None = None) -> None:
    """Run an INSERT / UPDATE / DELETE statement."""
    if _using_d1_binding_backend():
        await _d1_execute(sql, args or [])
        return

    await init_db()
    conn = get_client()
    conn.execute(sql, args or [])
    conn.commit()


async def fetch_one(sql: str, args: list[Any] | None = None) -> dict[str, Any] | None:
    """Return a single row as a dict, or None."""
    if _using_d1_binding_backend():
        return await _d1_fetch_one(sql, args or [])

    await init_db()
    conn = get_client()
    cursor = conn.execute(sql, args or [])
    row = cursor.fetchone()

    if not row:
        return None

    columns = [col[0] for col in cursor.description]
    return dict(zip(columns, row))


async def fetch_all(sql: str, args: list[Any] | None = None) -> list[dict[str, Any]]:
    """Return all rows as a list of dicts."""
    if _using_d1_binding_backend():
        return await _d1_fetch_all(sql, args or [])

    await init_db()
    conn = get_client()
    cursor = conn.execute(sql, args or [])
    rows = cursor.fetchall()

    if not rows:
        return []

    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


async def execute_batch(statements: list[tuple[str, list[Any]]]) -> None:
    """Execute multiple statements in a single transaction (atomic)."""
    if _using_d1_binding_backend():
        await _d1_execute_batch(statements)
        return

    await init_db()
    conn = get_client()
    try:
        for sql, args in statements:
            conn.execute(sql, args or [])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
