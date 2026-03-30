import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
def app_with_auth():
    return create_app()


@pytest.fixture
async def auth_client(app_with_auth):
    transport = ASGITransport(app=app_with_auth)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestGoogleAuthRedirect:
    @pytest.mark.asyncio
    async def test_returns_authorization_url(self, auth_client, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setattr(
            "app.core.config.settings.GOOGLE_REDIRECT_URI",
            "http://localhost:8000/api/v1/auth/google/callback",
        )

        mock_redis = AsyncMock()
        with patch("app.auth.router.get_redis", return_value=mock_redis):
            response = await auth_client.get("/api/v1/auth/google")

        assert response.status_code == 200
        data = response.json()
        assert "authorization_url" in data
        assert "accounts.google.com" in data["authorization_url"]


class TestRefreshEndpoint:
    @pytest.mark.asyncio
    async def test_rejects_missing_cookie(self, auth_client):
        response = await auth_client.post("/api/v1/auth/refresh")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_rejects_invalid_token(self, auth_client):
        @asynccontextmanager
        async def mock_db_session(*args, **kwargs):
            mock_session = AsyncMock()
            yield mock_session

        with patch("app.auth.router.get_db_session", mock_db_session):
            with patch(
                "app.auth.router.rotate_refresh_token",
                side_effect=ValueError("Refresh token not found"),
            ):
                response = await auth_client.post(
                    "/api/v1/auth/refresh",
                    cookies={"refresh_token": "invalid-token"},
                )
        assert response.status_code == 401


class TestLogoutEndpoint:
    @pytest.mark.asyncio
    async def test_rejects_unauthenticated(self, auth_client):
        """Logout requires a valid JWT."""
        response = await auth_client.post("/api/v1/auth/logout")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_clears_cookie(self, auth_client, rsa_keys):
        from app.core.security import create_access_token

        user_id = uuid.uuid4()
        token = create_access_token(user_id=user_id)

        @asynccontextmanager
        async def mock_db_session(*args, **kwargs):
            mock_session = AsyncMock()
            yield mock_session

        with patch("app.auth.router.get_db_session", mock_db_session):
            with patch("app.auth.router.revoke_refresh_token", new_callable=AsyncMock):
                response = await auth_client.post(
                    "/api/v1/auth/logout",
                    headers={"Authorization": f"Bearer {token}"},
                    cookies={"refresh_token": "some-token"},
                )
        assert response.status_code == 200
        set_cookie = response.headers.get("set-cookie", "")
        assert "refresh_token" in set_cookie
