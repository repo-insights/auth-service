"""
app/core/exceptions.py
───────────────────────
Domain-specific exception hierarchy.
Each exception maps cleanly to an HTTP status code via the global handler.
"""

from typing import Any, Dict, Optional


class AppException(Exception):
    """Base application exception."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred"

    def __init__(
        self,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message or self.__class__.message
        self.details = details or {}
        super().__init__(self.message)


# ── Auth Exceptions ───────────────────────────────────────────────────────────

class AuthenticationError(AppException):
    status_code = 401
    error_code = "AUTHENTICATION_FAILED"
    message = "Authentication failed"


class InvalidCredentialsError(AuthenticationError):
    error_code = "INVALID_CREDENTIALS"
    message = "Invalid email or password"


class AccountLockedError(AuthenticationError):
    status_code = 423
    error_code = "ACCOUNT_LOCKED"
    message = "Account is temporarily locked due to multiple failed login attempts"


class AccountNotVerifiedError(AuthenticationError):
    error_code = "ACCOUNT_NOT_VERIFIED"
    message = "Email address has not been verified"


class InvalidTokenError(AuthenticationError):
    error_code = "INVALID_TOKEN"
    message = "Token is invalid"


class TokenExpiredError(AuthenticationError):
    error_code = "TOKEN_EXPIRED"
    message = "Token has expired"


class RefreshTokenRevokedError(AuthenticationError):
    error_code = "TOKEN_REVOKED"
    message = "Refresh token has been revoked"


# ── Authorization Exceptions ──────────────────────────────────────────────────

class PermissionDeniedError(AppException):
    status_code = 403
    error_code = "PERMISSION_DENIED"
    message = "You do not have permission to perform this action"


class InsufficientScopesError(PermissionDeniedError):
    error_code = "INSUFFICIENT_SCOPES"
    message = "Token does not have the required scopes"


# ── Resource Exceptions ───────────────────────────────────────────────────────

class NotFoundError(AppException):
    status_code = 404
    error_code = "NOT_FOUND"
    message = "Resource not found"


class UserNotFoundError(NotFoundError):
    error_code = "USER_NOT_FOUND"
    message = "User not found"


class ConflictError(AppException):
    status_code = 409
    error_code = "CONFLICT"
    message = "Resource already exists"


class EmailAlreadyExistsError(ConflictError):
    error_code = "EMAIL_EXISTS"
    message = "An account with this email already exists"


# ── Validation Exceptions ─────────────────────────────────────────────────────

class ValidationError(AppException):
    status_code = 422
    error_code = "VALIDATION_ERROR"
    message = "Validation failed"


# ── External Service Exceptions ───────────────────────────────────────────────

class GoogleAuthError(AppException):
    status_code = 400
    error_code = "GOOGLE_AUTH_ERROR"
    message = "Google authentication failed"


class RateLimitExceededError(AppException):
    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"
    message = "Too many requests. Please try again later."
