import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
def otp_app():
    return create_app()


@pytest.fixture
async def otp_client(otp_app):
    transport = ASGITransport(app=otp_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestOtpRequest:
    @pytest.mark.asyncio
    async def test_sends_otp_successfully(self, otp_client):
        mock_redis = AsyncMock()
        with patch("app.auth.router.get_redis", return_value=mock_redis):
            with patch("app.auth.router.check_rate_limit", new_callable=AsyncMock, return_value=True):
                with patch("app.auth.router.generate_otp", return_value="123456"):
                    with patch("app.auth.router.store_otp", new_callable=AsyncMock):
                        with patch("app.auth.router.send_otp_sms", new_callable=AsyncMock):
                            resp = await otp_client.post(
                                "/api/v1/auth/otp/request",
                                json={"phone": "+919876543210"},
                            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["expires_in"] == 300

    @pytest.mark.asyncio
    async def test_rejects_invalid_phone_format(self, otp_client):
        resp = await otp_client.post(
            "/api/v1/auth/otp/request",
            json={"phone": "9876543210"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_rate_limits_otp_requests(self, otp_client):
        mock_redis = AsyncMock()
        with patch("app.auth.router.get_redis", return_value=mock_redis):
            with patch("app.auth.router.check_rate_limit", new_callable=AsyncMock, return_value=False):
                resp = await otp_client.post(
                    "/api/v1/auth/otp/request",
                    json={"phone": "+919876543210"},
                )

        assert resp.status_code == 429


class TestOtpVerify:
    @pytest.mark.asyncio
    async def test_verifies_otp_and_returns_tokens(self, otp_client, rsa_keys):
        mock_redis = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.phone = "+919876543210"
        mock_user.email = None
        mock_user.full_name = ""
        mock_user.avatar_url = None
        mock_user.is_active = True
        mock_user.email_verified = False
        mock_user.phone_verified = True
        mock_user.created_at = "2026-03-29T00:00:00Z"

        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        @asynccontextmanager
        async def fake_db_session(*args, **kwargs):
            yield mock_session

        with patch("app.auth.router.get_redis", return_value=mock_redis):
            with patch("app.auth.router.check_rate_limit", new_callable=AsyncMock, return_value=True):
                with patch("app.auth.router.verify_otp_from_redis", new_callable=AsyncMock, return_value=True):
                    with patch("app.auth.router.get_db_session", side_effect=fake_db_session):
                        with patch("app.auth.router.find_or_create_phone_user", new_callable=AsyncMock, return_value=(mock_user, True)):
                            with patch("app.auth.router.issue_token_pair", new_callable=AsyncMock, return_value=("jwt.token.here", "a" * 64)):
                                resp = await otp_client.post(
                                    "/api/v1/auth/otp/verify",
                                    json={"phone": "+919876543210", "otp": "123456"},
                                )

        assert resp.status_code == 201
        data = resp.json()
        assert data["success"] is True
        assert "access_token" in data["data"]

    @pytest.mark.asyncio
    async def test_rejects_invalid_otp_format(self, otp_client):
        resp = await otp_client.post(
            "/api/v1/auth/otp/verify",
            json={"phone": "+919876543210", "otp": "12345"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_returns_401_on_wrong_otp(self, otp_client):
        mock_redis = AsyncMock()
        with patch("app.auth.router.get_redis", return_value=mock_redis):
            with patch("app.auth.router.check_rate_limit", new_callable=AsyncMock, return_value=True):
                with patch("app.auth.router.verify_otp_from_redis", new_callable=AsyncMock, return_value=False):
                    resp = await otp_client.post(
                        "/api/v1/auth/otp/verify",
                        json={"phone": "+919876543210", "otp": "999999"},
                    )

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_rate_limits_verify_requests(self, otp_client):
        mock_redis = AsyncMock()
        with patch("app.auth.router.get_redis", return_value=mock_redis):
            with patch("app.auth.router.check_rate_limit", new_callable=AsyncMock, return_value=False):
                resp = await otp_client.post(
                    "/api/v1/auth/otp/verify",
                    json={"phone": "+919876543210", "otp": "123456"},
                )

        assert resp.status_code == 429
