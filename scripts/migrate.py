#!/usr/bin/env python3
"""
Run SQL migrations against the configured D1/Turso database.

Usage:
    python scripts/migrate.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.db.database import close_db, execute, init_db

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def _prepare_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []

    for raw_line in sql.splitlines():
        line = raw_line.strip()

        if not line or line.startswith("--"):
            continue

        # Remote libsql/D1 endpoints do not accept these PRAGMA statements.
        if line.upper().startswith("PRAGMA "):
            continue

        current.append(raw_line)
        chunk = "\n".join(current).strip()
        if chunk.endswith(";"):
            statements.append(chunk[:-1].strip())
            current = []

    tail = "\n".join(current).strip()
    if tail:
        statements.append(tail)

    return [stmt for stmt in statements if stmt]


async def run_migrations() -> None:
    if settings.db_backend == "d1_binding":
        raise RuntimeError(
            "scripts/migrate.py only supports DB_BACKEND=libsql. "
            "Use Cloudflare D1 migration tooling when running with DB_BACKEND=d1_binding."
        )

    await init_db()
    try:
        sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        if not sql_files:
            print("No migration files found.")
            return

        for sql_file in sql_files:
            print(f"Applying {sql_file.name} …")
            sql = sql_file.read_text()
            statements = _prepare_statements(sql)
            for stmt in statements:
                await execute(stmt)
            print(f"  ✓ {sql_file.name}")
        print("All migrations applied.")
    finally:
        await close_db()


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_migrations())
