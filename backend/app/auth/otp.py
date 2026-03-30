"""OTP generation, Redis storage, and MSG91 SMS integration."""

import hashlib
import json
import secrets

import httpx
import structlog
from redis.asyncio import Redis

from app.core.config import settings

logger = structlog.get_logger()

MSG91_SEND_OTP_URL = "https://control.msg91.com/api/v5/otp"
MAX_VERIFY_ATTEMPTS = 5
OTP_TTL_SECONDS = 300  # 5 minutes


def generate_otp() -> str:
    """Generate a cryptographically secure 6-digit OTP."""
    return f"{secrets.randbelow(1000000):06d}"


def hash_otp(otp: str) -> str:
    """SHA-256 hash of the OTP for storage. Never store raw OTPs."""
    return hashlib.sha256(otp.encode()).hexdigest()


async def store_otp(redis: Redis, phone: str, otp: str) -> None:
    """Store OTP hash in Redis with TTL and zero attempts."""
    data = json.dumps({"otp_hash": hash_otp(otp), "attempts": 0})
    await redis.set(f"otp:{phone}", data, ex=OTP_TTL_SECONDS)


async def verify_otp_from_redis(redis: Redis, phone: str, otp: str) -> bool:
    """Verify OTP against Redis store.

    Returns True if OTP matches (and deletes the key — single use).
    Returns False if OTP is wrong (increments attempt counter).
    Raises ValueError if expired or max attempts exceeded.
    """
    key = f"otp:{phone}"
    raw = await redis.get(key)

    if raw is None:
        raise ValueError("OTP expired or not requested")

    data = json.loads(raw)

    if data["attempts"] >= MAX_VERIFY_ATTEMPTS:
        await redis.delete(key)
        raise ValueError("Too many attempts — OTP invalidated")

    if hash_otp(otp) == data["otp_hash"]:
        await redis.delete(key)  # Single-use: delete after success
        return True

    # Wrong OTP — increment attempts, preserve remaining TTL
    data["attempts"] += 1
    ttl = await redis.ttl(key)
    if ttl > 0:
        await redis.set(key, json.dumps(data), ex=ttl)
    return False


async def send_otp_sms(phone: str, otp: str) -> None:
    """Send OTP via MSG91 Transactional SMS API.

    Raises:
        ValueError: If MSG91 API returns non-200 status.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            MSG91_SEND_OTP_URL,
            headers={
                "authkey": settings.MSG91_AUTH_KEY,
                "Content-Type": "application/json",
            },
            json={
                "template_id": settings.MSG91_TEMPLATE_ID,
                "mobile": phone.lstrip("+"),
                "otp": otp,
            },
        )

    if resp.status_code != 200:
        await logger.awarning("msg91_send_failed", status=resp.status_code)
        raise ValueError("Failed to send OTP via SMS")

    await logger.ainfo("otp_sent", phone_last4=phone[-4:])
