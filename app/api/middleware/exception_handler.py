"""
app/api/middleware/exception_handler.py
────────────────────────────────────────
Global exception handler that maps domain exceptions to RFC 7807-style
JSON error responses and logs them appropriately.
"""

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppException
from app.core.logging import get_logger

logger = get_logger(__name__)


def _error_response(
    status_code: int,
    error_code: str,
    message: str,
    details: dict | None = None,
) -> JSONResponse:
    body = {
        "error": {
            "code": error_code,
            "message": message,
        }
    }
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle all domain-specific AppException subclasses."""
    # Log server errors loudly; client errors quietly
    if exc.status_code >= 500:
        logger.error(
            "Internal error",
            error_code=exc.error_code,
            message=exc.message,
            path=str(request.url),
        )
    else:
        logger.info(
            "Client error",
            error_code=exc.error_code,
            message=exc.message,
            path=str(request.url),
        )

    return _error_response(
        status_code=exc.status_code,
        error_code=exc.error_code,
        message=exc.message,
        details=exc.details or None,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic v2 validation errors from request bodies."""
    errors = []
    for error in exc.errors():
        errors.append(
            {
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
        )

    logger.info(
        "Request validation failed",
        path=str(request.url),
        errors=errors,
    )

    return _error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error_code="VALIDATION_ERROR",
        message="Request validation failed",
        details={"errors": errors},
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Handle standard HTTP exceptions (e.g. 404 from routing)."""
    return _error_response(
        status_code=exc.status_code,
        error_code="HTTP_ERROR",
        message=exc.detail or "An HTTP error occurred",
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all for unexpected exceptions — never leak internals."""
    logger.exception(
        "Unhandled exception",
        path=str(request.url),
        exc_info=exc,
    )
    return _error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code="INTERNAL_ERROR",
        message="An unexpected error occurred. Please try again later.",
    )
