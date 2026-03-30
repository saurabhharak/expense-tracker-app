import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.auth.oauth import build_google_auth_url, exchange_google_code, GoogleUserInfo


class TestBuildGoogleAuthUrl:
    def test_returns_url_with_required_params(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setattr(
            "app.core.config.settings.GOOGLE_REDIRECT_URI",
            "http://localhost:8000/api/v1/auth/google/callback",
        )
        url, state = build_google_auth_url()
        assert "accounts.google.com" in url
        assert "test-client-id" in url
        assert "state=" in url
        assert len(state) > 0

    def test_state_is_unique_per_call(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setattr(
            "app.core.config.settings.GOOGLE_REDIRECT_URI",
            "http://localhost:8000/api/v1/auth/google/callback",
        )
        _, state1 = build_google_auth_url()
        _, state2 = build_google_auth_url()
        assert state1 != state2


class TestExchangeGoogleCode:
    @pytest.mark.asyncio
    async def test_returns_user_info_on_success(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setattr("app.core.config.settings.GOOGLE_CLIENT_SECRET", "test-secret")
        monkeypatch.setattr(
            "app.core.config.settings.GOOGLE_REDIRECT_URI",
            "http://localhost:8000/callback",
        )

        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {"access_token": "fake-access-token", "id_token": "fake.id.token"}

        mock_userinfo_response = MagicMock()
        mock_userinfo_response.status_code = 200
        mock_userinfo_response.json.return_value = {
            "sub": "google-123",
            "email": "user@gmail.com",
            "email_verified": True,
            "name": "Test User",
            "picture": "https://lh3.googleusercontent.com/photo.jpg",
        }

        with patch("app.auth.oauth.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = mock_token_response
            mock_client.get.return_value = mock_userinfo_response
            mock_client_cls.return_value = mock_client

            user_info = await exchange_google_code("auth-code-123")

        assert isinstance(user_info, GoogleUserInfo)
        assert user_info.google_id == "google-123"
        assert user_info.email == "user@gmail.com"
        assert user_info.full_name == "Test User"
        assert user_info.avatar_url == "https://lh3.googleusercontent.com/photo.jpg"

    @pytest.mark.asyncio
    async def test_raises_on_token_exchange_failure(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setattr("app.core.config.settings.GOOGLE_CLIENT_SECRET", "test-secret")
        monkeypatch.setattr(
            "app.core.config.settings.GOOGLE_REDIRECT_URI",
            "http://localhost:8000/callback",
        )

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "invalid_grant"

        with patch("app.auth.oauth.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            with pytest.raises(ValueError, match="Failed to exchange"):
                await exchange_google_code("bad-code")
