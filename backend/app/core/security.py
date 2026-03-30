"""Security utilities: JWT creation, refresh token generation and hashing."""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.config import settings


def create_access_token(user_id: uuid.UUID, email: str | None) -> str:
    """Create a signed RS256 JWT access token.

    The token payload contains only user_id (sub) and email.
    Email is included for convenience but is non-sensitive in this context
    (it is already part of the user's own session).
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": expire,
    }
    private_key = _load_private_key()
    return jwt.encode(payload, private_key, algorithm=settings.JWT_ALGORITHM)


def generate_refresh_token() -> str:
    """Generate a cryptographically secure 32-byte hex refresh token (64 chars)."""
    return secrets.token_hex(32)


def hash_refresh_token(token_raw: str) -> str:
    """Hash a raw refresh token with SHA-256 for safe storage."""
    return hashlib.sha256(token_raw.encode()).hexdigest()


def _load_private_key() -> str:
    with open(settings.JWT_PRIVATE_KEY_PATH) as f:
        return f.read()


def _load_public_key() -> str:
    with open(settings.JWT_PUBLIC_KEY_PATH) as f:
        return f.read()
