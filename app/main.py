"""
app/main.py
────────────
FastAPI application factory.
Registers middleware, routers, exception handlers, and lifecycle hooks.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.middleware.exception_handler import (
    app_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.api.middleware.logging import RequestLoggingMiddleware
from app.api.middleware.rate_limiter import RateLimitMiddleware
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.database import engine
from app.core.exceptions import AppException
from app.core.logging import configure_logging, get_logger
from app.core.redis import close_redis, get_redis

logger = get_logger(__name__)


# ── Application lifecycle ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle manager."""
    # ── Startup ────────────────────────────────────────────────
    configure_logging()
    logger.info(
        "Starting AuthService",
        env=settings.APP_ENV,
        version="1.0.0",
    )

    # Warm up Redis connection
    try:
        redis = await get_redis()
        await redis.ping()
        logger.info("Redis connection healthy")
    except Exception as exc:
        logger.warning("Redis not available at startup", error=str(exc))

    logger.info("AuthService ready")

    yield  # ← Application runs here

    # ── Shutdown ───────────────────────────────────────────────
    logger.info("Shutting down AuthService")
    await close_redis()
    await engine.dispose()
    logger.info("AuthService stopped")


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description=(
            "Production-grade authentication microservice with JWT (RSA), "
            "Google OAuth 2.0, refresh token rotation, RBAC, and scope-based authorization."
        ),
        version="1.0.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )

    # ── Custom middleware (order matters: outermost runs first) ──
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)

    # ── Exception handlers ────────────────────────────────────
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # ── Routers ───────────────────────────────────────────────
    app.include_router(api_v1_router)

    # ── Health check ──────────────────────────────────────────
    @app.get("/health", tags=["Health"], include_in_schema=False)
    async def health_check():
        return {"status": "ok", "service": settings.APP_NAME}

    return app


app = create_app()
