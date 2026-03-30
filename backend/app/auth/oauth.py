"""Google OAuth2 authorization code flow."""

import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


@dataclass(frozen=True)
class GoogleUserInfo:
    google_id: str
    email: str | None
    email_verified: bool
    full_name: str
    avatar_url: str | None


def build_google_auth_url() -> tuple[str, str]:
    """Build Google OAuth2 authorization URL.

    Returns:
        (authorization_url, state) — state must be stored (e.g. in Redis)
        and verified on callback to prevent CSRF.
    """
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "state": state,
        "prompt": "consent",
    }
    url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return url, state


async def exchange_google_code(code: str) -> GoogleUserInfo:
    """Exchange authorization code for user info.

    1. POST to Google's token endpoint to get tokens.
    2. GET Google's userinfo endpoint with the access token.

    Raises:
        ValueError: If token exchange or userinfo fetch fails.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Step 1: Exchange code for tokens
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            await logger.awarning("google_token_exchange_failed", status=token_resp.status_code)
            raise ValueError("Failed to exchange authorization code with Google")

        tokens = token_resp.json()
        access_token = tokens.get("access_token")
        if not access_token:
            raise ValueError("Failed to exchange authorization code with Google")

        # Step 2: Get user info
        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            await logger.awarning("google_userinfo_failed", status=userinfo_resp.status_code)
            raise ValueError("Failed to fetch user info from Google")

        info = userinfo_resp.json()

    return GoogleUserInfo(
        google_id=info["sub"],
        email=info.get("email"),
        email_verified=info.get("email_verified", False),
        full_name=info.get("name", ""),
        avatar_url=info.get("picture"),
    )
