"""Google OAuth2 helpers and data models."""

from pydantic import BaseModel


class GoogleUserInfo(BaseModel):
    """Parsed Google user info returned from token verification."""

    google_id: str
    email: str | None
    email_verified: bool
    full_name: str | None
    avatar_url: str | None
