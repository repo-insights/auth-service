"""Global exception handlers — normalise all error responses to a consistent JSON shape."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from jose import JWTError

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        errors = [
            {
                "field": ".".join(str(loc) for loc in err["loc"] if loc != "body"),
                "message": err["msg"],
                "code": "validation_error",
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"errors": errors},
        )

    @app.exception_handler(JWTError)
    async def jwt_error_handler(request: Request, exc: JWTError):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "invalid_token", "message": str(exc)},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "internal_error", "message": "An unexpected error occurred"},
        )
