import hashlib
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.auth.otp import generate_otp, hash_otp, store_otp, verify_otp_from_redis, send_otp_sms


class TestGenerateOtp:
    def test_returns_6_digit_string(self):
        otp = generate_otp()
        assert len(otp) == 6
        assert otp.isdigit()

    def test_is_random(self):
        otps = {generate_otp() for _ in range(20)}
        assert len(otps) > 1


class TestHashOtp:
    def test_returns_sha256_hex(self):
        h = hash_otp("123456")
        assert len(h) == 64
        expected = hashlib.sha256("123456".encode()).hexdigest()
        assert h == expected

    def test_deterministic(self):
        assert hash_otp("999999") == hash_otp("999999")


class TestStoreOtp:
    @pytest.mark.asyncio
    async def test_stores_hash_and_attempts_in_redis(self):
        mock_redis = AsyncMock()
        await store_otp(mock_redis, "+919876543210", "123456")

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        key = call_args[0][0]
        value = json.loads(call_args[0][1])

        assert key == "otp:+919876543210"
        assert value["attempts"] == 0
        assert value["otp_hash"] == hash_otp("123456")
        assert call_args[1]["ex"] == 300


class TestVerifyOtpFromRedis:
    @pytest.mark.asyncio
    async def test_returns_true_on_correct_otp(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps({
            "otp_hash": hash_otp("123456"),
            "attempts": 0,
        })

        result = await verify_otp_from_redis(mock_redis, "+919876543210", "123456")
        assert result is True
        mock_redis.delete.assert_called_once_with("otp:+919876543210")

    @pytest.mark.asyncio
    async def test_returns_false_on_wrong_otp(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps({
            "otp_hash": hash_otp("123456"),
            "attempts": 1,
        })
        mock_redis.ttl.return_value = 250

        result = await verify_otp_from_redis(mock_redis, "+919876543210", "999999")
        assert result is False
        mock_redis.set.assert_called_once()
        updated = json.loads(mock_redis.set.call_args[0][1])
        assert updated["attempts"] == 2

    @pytest.mark.asyncio
    async def test_raises_on_expired_otp(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        with pytest.raises(ValueError, match="expired"):
            await verify_otp_from_redis(mock_redis, "+919876543210", "123456")

    @pytest.mark.asyncio
    async def test_raises_on_max_attempts(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps({
            "otp_hash": hash_otp("123456"),
            "attempts": 5,
        })

        with pytest.raises(ValueError, match="Too many attempts"):
            await verify_otp_from_redis(mock_redis, "+919876543210", "123456")
        mock_redis.delete.assert_called_once_with("otp:+919876543210")


class TestSendOtpSms:
    @pytest.mark.asyncio
    async def test_calls_msg91_api(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.MSG91_AUTH_KEY", "test-auth-key")
        monkeypatch.setattr("app.core.config.settings.MSG91_TEMPLATE_ID", "test-template")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"type": "success"}

        with patch("app.auth.otp.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            await send_otp_sms("+919876543210", "123456")

        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_api_failure(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.MSG91_AUTH_KEY", "test-auth-key")
        monkeypatch.setattr("app.core.config.settings.MSG91_TEMPLATE_ID", "test-template")

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"

        with patch("app.auth.otp.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            with pytest.raises(ValueError, match="Failed to send OTP"):
                await send_otp_sms("+919876543210", "123456")
