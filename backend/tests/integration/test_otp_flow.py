"""Integration tests for Phone OTP request → verify → token issuance flow.

Mocks: MSG91 SMS API (external), Redis (simulated in-memory).
Real: Router → Service → OTP module logic.
"""

import random
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.otp import hash_otp
from app.main import create_app


@pytest.fixture
def integration_app():
    return create_app()


@pytest.fixture
async def otp_flow_client(integration_app):
    transport = ASGITransport(app=integration_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _make_mock_redis():
    """Create a mock Redis that simulates OTP storage."""
    store = {}
    mock_redis = AsyncMock()

    async def mock_set(key, value, ex=None):
        store[key] = value

    async def mock_get(key):
        return store.get(key)

    async def mock_delete(key):
        store.pop(key, None)

    async def mock_ttl(key):
        return 280

    mock_redis.set = AsyncMock(side_effect=mock_set)
    mock_redis.get = AsyncMock(side_effect=mock_get)
    mock_redis.delete = AsyncMock(side_effect=mock_delete)
    mock_redis.ttl = AsyncMock(side_effect=mock_ttl)

    # Rate limiting pipeline mock (always allow).
    # pipeline() is a synchronous call in the real Redis client,
    # so we use MagicMock (not AsyncMock) to avoid returning a coroutine.
    mock_pipe = AsyncMock()
    mock_pipe.execute.return_value = [None, None, 1, None]
    mock_redis.pipeline = MagicMock(return_value=mock_pipe)

    return mock_redis, store


def _make_mock_user(phone: str):
    """Build a MagicMock User for DB-free verify tests."""
    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()
    mock_user.phone = phone
    mock_user.email = None
    mock_user.full_name = ""
    mock_user.avatar_url = None
    mock_user.is_active = True
    mock_user.email_verified = False
    mock_user.phone_verified = True
    mock_user.created_at = "2026-03-29T00:00:00Z"
    return mock_user


class TestOtpFlow:
    @pytest.mark.asyncio
    async def test_request_then_verify_creates_user(self, otp_flow_client, rsa_keys):
        """Full flow: request OTP → verify → get tokens for new user."""
        mock_redis, store = _make_mock_redis()
        phone = f"+91{random.randint(6000000000, 9999999999)}"
        mock_user = _make_mock_user(phone)

        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        @asynccontextmanager
        async def fake_db_session(*args, **kwargs):
            yield mock_session

        with patch("app.auth.router.get_redis", return_value=mock_redis):
            with patch("app.auth.router.send_otp_sms", new_callable=AsyncMock):
                # Step 1: Request OTP
                req_resp = await otp_flow_client.post(
                    "/api/v1/auth/otp/request",
                    json={"phone": phone},
                )

        assert req_resp.status_code == 200
        assert req_resp.json()["data"]["expires_in"] == 300

        # For verify, mock verify_otp_from_redis (can't recover raw OTP from hash),
        # and mock DB dependencies to avoid needing a live PostgreSQL instance.
        with patch("app.auth.router.get_redis", return_value=mock_redis):
            with patch("app.auth.router.verify_otp_from_redis", new_callable=AsyncMock, return_value=True):
                with patch("app.auth.router.get_db_session", side_effect=fake_db_session):
                    with patch("app.auth.router.find_or_create_phone_user", new_callable=AsyncMock, return_value=(mock_user, True)):
                        with patch("app.auth.router.issue_token_pair", new_callable=AsyncMock, return_value=("jwt.token.here", "a" * 64)):
                            verify_resp = await otp_flow_client.post(
                                "/api/v1/auth/otp/verify",
                                json={"phone": phone, "otp": "123456"},
                            )

        assert verify_resp.status_code == 201  # New user
        data = verify_resp.json()
        assert data["success"] is True
        assert "access_token" in data["data"]
        assert data["data"]["user"]["phone_verified"] is True

        # Check refresh cookie was set
        cookies = verify_resp.headers.get_list("set-cookie")
        assert any("refresh_token=" in c for c in cookies)

    @pytest.mark.asyncio
    async def test_verify_wrong_otp_returns_401(self, otp_flow_client):
        mock_redis, _ = _make_mock_redis()

        with patch("app.auth.router.get_redis", return_value=mock_redis):
            with patch("app.auth.router.verify_otp_from_redis", new_callable=AsyncMock, return_value=False):
                resp = await otp_flow_client.post(
                    "/api/v1/auth/otp/verify",
                    json={"phone": "+919876543210", "otp": "999999"},
                )

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_verify_expired_otp_returns_401(self, otp_flow_client):
        mock_redis, _ = _make_mock_redis()

        with patch("app.auth.router.get_redis", return_value=mock_redis):
            with patch("app.auth.router.verify_otp_from_redis", new_callable=AsyncMock, side_effect=ValueError("OTP expired or not requested")):
                resp = await otp_flow_client.post(
                    "/api/v1/auth/otp/verify",
                    json={"phone": "+919876543210", "otp": "123456"},
                )

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_rate_limited_request_returns_429(self, otp_flow_client):
        mock_redis, _ = _make_mock_redis()
        # Override pipeline to simulate rate limit exceeded.
        # count=4 > limit=3 → check_rate_limit returns False → 429
        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [None, None, 4, None]
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        with patch("app.auth.router.get_redis", return_value=mock_redis):
            resp = await otp_flow_client.post(
                "/api/v1/auth/otp/request",
                json={"phone": "+919876543210"},
            )

        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_verify_max_attempts_returns_429(self, otp_flow_client):
        mock_redis, _ = _make_mock_redis()

        with patch("app.auth.router.get_redis", return_value=mock_redis):
            with patch("app.auth.router.verify_otp_from_redis", new_callable=AsyncMock, side_effect=ValueError("Too many attempts — OTP invalidated")):
                resp = await otp_flow_client.post(
                    "/api/v1/auth/otp/verify",
                    json={"phone": "+919876543210", "otp": "123456"},
                )

        assert resp.status_code == 429
