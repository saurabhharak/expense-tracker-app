"""Auth business logic: user management, token issuance, rotation, revocation."""

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import RefreshToken, User
from app.auth.oauth import GoogleUserInfo
from app.core.config import settings
from app.core.security import create_access_token, generate_refresh_token, hash_refresh_token

logger = structlog.get_logger()


async def find_or_create_google_user(
    session: AsyncSession,
    google_info: GoogleUserInfo,
) -> tuple[User, bool]:
    """Find existing user by google_id, link by email, or create new.

    Returns:
        (user, created) — created is True if a new user was inserted.
    """
    # 1. Look up by google_id
    result = await session.execute(
        select(User).where(User.google_id == google_info.google_id)
    )
    user = result.scalar_one_or_none()
    if user:
        if not user.is_active:
            raise ValueError("Account is deactivated")
        return user, False

    # 2. Look up by verified email (to link accounts)
    if google_info.email and google_info.email_verified:
        result = await session.execute(
            select(User).where(User.email == google_info.email)
        )
        user = result.scalar_one_or_none()
        if user:
            if not user.is_active:
                raise ValueError("Account is deactivated")
            # Link Google account to existing user
            user.google_id = google_info.google_id
            if google_info.avatar_url and not user.avatar_url:
                user.avatar_url = google_info.avatar_url
            user.email_verified = True
            await session.flush()
            await logger.ainfo("google_account_linked", user_id=str(user.id))
            return user, False

    # 3. Create new user
    user = User(
        email=google_info.email if google_info.email_verified else None,
        google_id=google_info.google_id,
        full_name=google_info.full_name,
        avatar_url=google_info.avatar_url,
        email_verified=google_info.email_verified,
    )
    session.add(user)
    await session.flush()
    await logger.ainfo("user_created_via_google", user_id=str(user.id))
    return user, True


async def issue_token_pair(
    session: AsyncSession,
    user: User,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, str]:
    """Issue a JWT access token and a new refresh token.

    Returns:
        (access_token, refresh_token_raw) — refresh_token_raw is the
        unhashed value that goes into the cookie.
    """
    access_token = create_access_token(user_id=user.id)

    refresh_raw = generate_refresh_token()
    refresh_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(refresh_raw),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=user_agent,
        ip_address=ip_address,
    )
    session.add(refresh_record)
    await session.flush()

    return access_token, refresh_raw


async def rotate_refresh_token(
    session: AsyncSession,
    old_token_raw: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, str]:
    """Rotate a refresh token: revoke the old, issue a new pair.

    Implements refresh token reuse detection per security spec:
    if a revoked token is presented, the entire family is revoked.

    Returns:
        (access_token, new_refresh_token_raw)

    Raises:
        ValueError: If the token is not found, expired, or already revoked.
    """
    old_hash = hash_refresh_token(old_token_raw)

    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == old_hash)
    )
    old_record = result.scalar_one_or_none()

    if old_record is None:
        raise ValueError("Refresh token not found")

    if old_record.expires_at < datetime.now(timezone.utc):
        raise ValueError("Refresh token expired")

    # Reuse detection: if token is already revoked, someone may have stolen it
    if old_record.revoked_at is not None:
        await _revoke_token_family(session, old_record.user_id)
        await logger.awarning("refresh_token_reuse_detected", user_id=str(old_record.user_id))
        raise ValueError("Refresh token reuse detected — all sessions revoked")

    # Revoke the old token
    old_record.revoked_at = datetime.now(timezone.utc)

    # Fetch user for new access token
    user_result = await session.execute(
        select(User).where(User.id == old_record.user_id)
    )
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise ValueError("User not found or deactivated")

    # Issue new pair
    access_token, new_refresh_raw = await issue_token_pair(
        session, user, user_agent=user_agent, ip_address=ip_address
    )

    # Link old → new for audit trail
    new_hash = hash_refresh_token(new_refresh_raw)
    new_result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == new_hash)
    )
    new_record = new_result.scalar_one_or_none()
    if new_record:
        old_record.replaced_by = new_record.id

    return access_token, new_refresh_raw


async def _revoke_token_family(session: AsyncSession, user_id) -> None:
    """Revoke ALL active refresh tokens for a user (nuclear option on reuse)."""
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    await logger.awarning("token_family_revoked", user_id=str(user_id))


async def revoke_refresh_token(session: AsyncSession, token_raw: str) -> None:
    """Revoke a single refresh token (used by logout)."""
    token_hash = hash_refresh_token(token_raw)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    record = result.scalar_one_or_none()
    if record and record.revoked_at is None:
        record.revoked_at = datetime.now(timezone.utc)
