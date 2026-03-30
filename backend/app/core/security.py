"""JWT access token creation and verification (RS256)."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError, jwt

from app.core.config import settings


def _load_key(path: str) -> str:
    with open(path) as f:
        return f.read()


def create_access_token(user_id: UUID) -> str:
    """Create a signed JWT access token. Only contains user_id (no PII)."""
    now = datetime.now(timezone.utc)
    payload: dict = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    private_key = _load_key(settings.JWT_PRIVATE_KEY_PATH)
    return jwt.encode(payload, private_key, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token. Raises JWTError on failure."""
    public_key = _load_key(settings.JWT_PUBLIC_KEY_PATH)
    payload = jwt.decode(token, public_key, algorithms=[settings.JWT_ALGORITHM])
    if payload.get("type") != "access":
        raise JWTError("Invalid token type")
    return payload


def generate_refresh_token() -> str:
    """Generate a 64-char hex opaque refresh token."""
    return secrets.token_hex(32)


def hash_refresh_token(token: str) -> str:
    """SHA-256 hash for storing refresh tokens in the database."""
    return hashlib.sha256(token.encode()).hexdigest()
