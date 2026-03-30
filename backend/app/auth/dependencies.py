"""FastAPI dependencies for authentication and database sessions with RLS."""

from fastapi import Depends, HTTPException, Request
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import decode_access_token


async def get_current_user(request: Request) -> str:
    """Extract and validate JWT from Authorization header.

    Returns:
        user_id (str) — UUID string from the token's 'sub' claim.

    Raises:
        HTTPException(401): If the token is missing, invalid, or expired.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authentication token")

    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    try:
        payload = decode_access_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return user_id


async def get_current_user_optional(request: Request) -> str | None:
    """Like get_current_user but returns None instead of raising."""
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


async def get_db(user_id: str = Depends(get_current_user)):
    """Provide an async DB session with RLS context set for the authenticated user."""
    async with get_db_session(user_id=user_id) as session:
        yield session
