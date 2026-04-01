"""
RepoInsight Auth Service — application factory.
"""

from __future__ import annotations

import logging
import logging.config

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.database import close_db, init_db
from app.middleware.exceptions import register_exception_handlers
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.worker_bindings import WorkerBindingMiddleware

# ─────────────────────────────────────────
# Logging setup
# ─────────────────────────────────────────

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        }
    },
    "root": {"level": "DEBUG" if settings.debug else "INFO", "handlers": ["console"]},
})


# ─────────────────────────────────────────
# App factory
# ─────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="RepoInsight Auth Service",
        description="Authentication, user management, and token issuance for RepoInsight.",
        version="1.0.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # CORS — tighten allowed_origins in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(WorkerBindingMiddleware)

    register_exception_handlers(app)

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    @app.on_event("startup")
    async def on_startup() -> None:
        await init_db()

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        await close_db()

    # ── Routes ─────────────────────────────────────────────────────────────────
    app.include_router(api_router)

    @app.get("/health", tags=["Health"])
    async def health() -> dict:
        return {"status": "ok", "service": settings.app_name}

    return app


app = create_app()
