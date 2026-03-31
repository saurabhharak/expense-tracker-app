"""Auth endpoints: Google OAuth2, OTP phone auth, token refresh, logout."""

import structlog
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.auth.dependencies import get_current_user
from app.auth.oauth import build_google_auth_url, exchange_google_code
from app.auth.otp import generate_otp, send_otp_sms, store_otp, verify_otp_from_redis
from app.auth.schemas import GoogleAuthURLResponse, OtpRequestSchema, OtpSentResponse, OtpVerifySchema, TokenResponse, UserResponse
from app.auth.service import (
    find_or_create_google_user,
    find_or_create_phone_user,
    issue_token_pair,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.core.config import settings
from app.core.database import get_db_session
from app.core.limiter import limiter
from app.core.rate_limit import check_rate_limit
from app.core.redis import get_redis

logger = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])

# Cookie config constants
REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_MAX_AGE = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: JSONResponse, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=REFRESH_COOKIE_MAX_AGE,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="strict",
    )


def _clear_refresh_cookie(response: JSONResponse) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="strict",
    )


@router.get("/google", response_model=GoogleAuthURLResponse)
@limiter.limit("20/minute")
async def google_auth_redirect(request: Request):
    """Return Google OAuth2 authorization URL. Frontend redirects user there."""
    url, state = build_google_auth_url()

    # Store state in Redis with 10-minute TTL for CSRF verification
    redis = get_redis()
    await redis.set(f"oauth_state:{state}", "1", ex=600)

    return GoogleAuthURLResponse(authorization_url=url)


@router.get("/google/callback")
@limiter.limit("10/minute")
async def google_callback(
    request: Request,
    code: str,
    state: str,
):
    """Handle Google OAuth2 callback. Exchanges code for tokens, creates/finds user."""
    # Verify state (CSRF protection)
    redis = get_redis()
    stored = await redis.get(f"oauth_state:{state}")
    if not stored:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    await redis.delete(f"oauth_state:{state}")

    # Exchange code for Google user info
    try:
        google_info = await exchange_google_code(code)
    except ValueError as e:
        await logger.awarning("google_oauth_failed")
        raise HTTPException(status_code=400, detail="Google authentication failed")

    # Find or create user
    async with get_db_session() as session:
        try:
            user, created = await find_or_create_google_user(session, google_info)
        except ValueError:
            raise HTTPException(status_code=401, detail="Authentication failed")

        user_agent = request.headers.get("User-Agent")
        ip_address = request.client.host if request.client else None

        access_token, refresh_raw = await issue_token_pair(
            session=session,
            user=user,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        user_data = UserResponse.model_validate(user)

    response_data = TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_data,
    )

    response = JSONResponse(
        status_code=201 if created else 200,
        content={"success": True, "data": response_data.model_dump(mode="json")},
    )
    _set_refresh_cookie(response, refresh_raw)

    await logger.ainfo(
        "google_auth_success",
        user_id=str(user.id) if hasattr(user, "id") else "unknown",
        created=created,
    )
    return response


@router.post("/refresh")
@limiter.limit("30/minute")
async def refresh_token(
    request: Request,
    refresh_token: str | None = Cookie(None, alias=REFRESH_COOKIE_NAME),
):
    """Rotate refresh token and issue new access token."""
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    user_agent = request.headers.get("User-Agent")
    ip_address = request.client.host if request.client else None

    async with get_db_session() as session:
        try:
            access_token, new_refresh_raw = await rotate_refresh_token(
                session=session,
                old_token_raw=refresh_token,
                user_agent=user_agent,
                ip_address=ip_address,
            )
        except ValueError as e:
            error_msg = str(e)
            if "reuse detected" in error_msg:
                await logger.awarning("refresh_token_reuse")
            raise HTTPException(status_code=401, detail="Invalid refresh token")

    response = JSONResponse(
        content={"success": True, "data": {"access_token": access_token, "token_type": "bearer"}},
    )
    _set_refresh_cookie(response, new_refresh_raw)
    return response


@router.post("/logout")
@limiter.limit("10/minute")
async def logout(
    request: Request,
    user_id: str = Depends(get_current_user),
    refresh_token: str | None = Cookie(None, alias=REFRESH_COOKIE_NAME),
):
    """Revoke current refresh token and clear the cookie."""
    if refresh_token:
        async with get_db_session() as session:
            await revoke_refresh_token(session, refresh_token)

    response = JSONResponse(content={"success": True, "data": {"message": "Logged out"}})
    _clear_refresh_cookie(response)

    await logger.ainfo("user_logged_out", user_id=user_id)
    return response


@router.post("/otp/request")
@limiter.limit("10/minute")
async def request_otp(request: Request, body: OtpRequestSchema):
    """Send a 6-digit OTP to the given phone number."""
    redis = get_redis()

    # Phone-specific rate limit: 3 per 10 minutes
    allowed = await check_rate_limit(redis, f"otp_send:{body.phone}", limit=3, window_seconds=600)
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many OTP requests. Try again later.")

    otp = generate_otp()

    try:
        await send_otp_sms(body.phone, otp)
    except ValueError:
        raise HTTPException(status_code=502, detail="Failed to send OTP. Try again later.")

    # Store AFTER successful SMS delivery — avoids wasting rate-limit slots on failures
    await store_otp(redis, body.phone, otp)

    await logger.ainfo("otp_requested", phone_last4=body.phone[-4:])

    return JSONResponse(
        content={"success": True, "data": OtpSentResponse().model_dump()},
    )


@router.post("/otp/verify")
@limiter.limit("10/minute")
async def verify_otp(request: Request, body: OtpVerifySchema):
    """Verify OTP and issue tokens. Auto-creates account on first verification."""
    redis = get_redis()

    # Phone-specific rate limit: 5 verify attempts per 15 minutes
    allowed = await check_rate_limit(redis, f"otp_verify:{body.phone}", limit=5, window_seconds=900)
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many verification attempts. Try again later.")

    try:
        is_valid = await verify_otp_from_redis(redis, body.phone, body.otp)
    except ValueError as e:
        error_msg = str(e)
        if "Too many attempts" in error_msg:
            raise HTTPException(status_code=429, detail="OTP invalidated due to too many attempts")
        raise HTTPException(status_code=401, detail="OTP expired or not requested")

    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid OTP")

    # OTP valid — find or create user, issue tokens
    async with get_db_session() as session:
        try:
            user, created = await find_or_create_phone_user(session, body.phone)
        except ValueError:
            raise HTTPException(status_code=401, detail="Authentication failed")

        user_agent = request.headers.get("User-Agent")
        ip_address = request.client.host if request.client else None

        access_token, refresh_raw = await issue_token_pair(
            session=session,
            user=user,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        user_data = UserResponse.model_validate(user)

    response_data = TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_data,
    )

    response = JSONResponse(
        status_code=201 if created else 200,
        content={"success": True, "data": response_data.model_dump(mode="json")},
    )
    _set_refresh_cookie(response, refresh_raw)

    await logger.ainfo("otp_auth_success", user_id=str(user.id), created=created)
    return response
