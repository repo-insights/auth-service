"""
app/services/google_oauth_service.py
──────────────────────────────────────
Verifies Google ID tokens using Google's public keys.
Uses the google-auth library for robust verification.
"""

from typing import Any, Dict

import httpx
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.core.config import settings
from app.core.exceptions import GoogleAuthError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Google's JWKS / token-info endpoint (fallback verification)
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


class GoogleOAuthService:
    async def verify_id_token(self, token: str) -> Dict[str, Any]:
        """
        Verify a Google ID token and return its claims.

        Uses google-auth's synchronous verifier (runs in threadpool for async).
        Falls back to Google's tokeninfo endpoint if client ID not configured.

        Returns a dict with at minimum: sub, email, email_verified.
        """
        if not settings.GOOGLE_CLIENT_ID:
            # Fallback: call Google's tokeninfo endpoint directly
            return await self._verify_via_tokeninfo(token)

        try:
            # google-auth is synchronous; wrap in executor for async contexts
            import asyncio
            loop = asyncio.get_event_loop()
            claims = await loop.run_in_executor(
                None,
                self._sync_verify,
                token,
            )
            return claims
        except Exception as exc:
            logger.warning("google-auth verification failed", error=str(exc))
            raise GoogleAuthError(f"Google token verification failed: {exc}") from exc

    def _sync_verify(self, token: str) -> Dict[str, Any]:
        request = google_requests.Request()
        claims = google_id_token.verify_oauth2_token(
            token,
            request,
            settings.GOOGLE_CLIENT_ID,
        )
        if not claims.get("email_verified"):
            raise GoogleAuthError("Google account email is not verified")
        return claims

    async def _verify_via_tokeninfo(self, token: str) -> Dict[str, Any]:
        """Verify by calling Google's tokeninfo endpoint (no client_id required)."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                GOOGLE_TOKENINFO_URL,
                params={"id_token": token},
            )

        if response.status_code != 200:
            raise GoogleAuthError("Google tokeninfo verification failed")

        data = response.json()

        if "error" in data:
            raise GoogleAuthError(f"Google error: {data['error']}")

        if not data.get("email_verified") in (True, "true"):
            raise GoogleAuthError("Google account email is not verified")

        return data
