"""Integration tests for the full Google OAuth2 → refresh → logout flow.

These tests mock external services (Google API, Redis) but test all internal
components working together through HTTP requests.

REQUIREMENT: PostgreSQL must be running with the expense_tracker schema and
users/refresh_tokens tables created. Run migrations before running these tests:
    docker-compose up -d postgres
    python -m alembic upgrade 001

Tests in this file share a class-scoped event loop to avoid asyncpg connection
pool teardown issues that occur when each test function has its own event loop.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.auth.oauth import GoogleUserInfo
from app.main import create_app


@pytest.fixture(scope="class")
def integration_app():
    return create_app()


@pytest_asyncio.fixture(scope="class", loop_scope="class")
async def integration_client(integration_app):
    transport = ASGITransport(app=integration_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _mock_google_exchange(google_id: str, email: str, name: str):
    """Return a patch context that mocks exchange_google_code."""
    return patch(
        "app.auth.router.exchange_google_code",
        new_callable=AsyncMock,
        return_value=GoogleUserInfo(
            google_id=google_id,
            email=email,
            email_verified=True,
            full_name=name,
            avatar_url=None,
        ),
    )


def _mock_redis_state_valid():
    """Return a patch context for valid OAuth state in Redis."""
    mock_redis = AsyncMock()
    mock_redis.get.return_value = "1"
    return patch("app.auth.router.get_redis", return_value=mock_redis)


@pytest.mark.asyncio(loop_scope="class")
class TestGoogleOAuthFlow:
    """Test the Google OAuth → refresh → logout flow end-to-end."""

    async def test_google_auth_url_contains_required_params(
        self, integration_client, monkeypatch
    ):
        monkeypatch.setattr("app.core.config.settings.GOOGLE_CLIENT_ID", "test-id")
        monkeypatch.setattr(
            "app.core.config.settings.GOOGLE_REDIRECT_URI",
            "http://localhost:8000/api/v1/auth/google/callback",
        )
        mock_redis = AsyncMock()
        with patch("app.auth.router.get_redis", return_value=mock_redis):
            resp = await integration_client.get("/api/v1/auth/google")

        assert resp.status_code == 200
        url = resp.json()["authorization_url"]
        assert "response_type=code" in url
        assert "scope=" in url
        assert "state=" in url

    async def test_callback_creates_user_and_returns_tokens(
        self, integration_client, rsa_keys
    ):
        """Full callback flow: exchange code → create user → return tokens + cookie."""
        google_id = f"g-{uuid.uuid4().hex}"
        email = f"test-{uuid.uuid4().hex[:8]}@gmail.com"

        with _mock_google_exchange(google_id, email, "Test User"):
            with _mock_redis_state_valid():
                resp = await integration_client.get(
                    "/api/v1/auth/google/callback",
                    params={"code": "test-auth-code", "state": "valid-state"},
                )

        assert resp.status_code == 201  # New user created
        data = resp.json()
        assert data["success"] is True
        assert "access_token" in data["data"]
        assert data["data"]["user"]["email"] == email
        assert data["data"]["user"]["full_name"] == "Test User"
        assert data["data"]["token_type"] == "bearer"
        assert data["data"]["expires_in"] > 0

        # Refresh token should be in Set-Cookie
        cookies = resp.headers.get_list("set-cookie")
        assert any("refresh_token=" in c for c in cookies)

    async def test_callback_returns_existing_user(self, integration_client, rsa_keys):
        """Second login with same google_id returns 200, not 201."""
        google_id = f"g-{uuid.uuid4().hex}"
        email = f"repeat-{uuid.uuid4().hex[:8]}@gmail.com"

        with _mock_google_exchange(google_id, email, "Repeat User"):
            with _mock_redis_state_valid():
                resp1 = await integration_client.get(
                    "/api/v1/auth/google/callback",
                    params={"code": "code1", "state": "state1"},
                )
                assert resp1.status_code == 201

                resp2 = await integration_client.get(
                    "/api/v1/auth/google/callback",
                    params={"code": "code2", "state": "state2"},
                )
                assert resp2.status_code == 200

    async def test_callback_rejects_invalid_state(self, integration_client):
        """Missing or invalid state should return 400."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # State not found
        with patch("app.auth.router.get_redis", return_value=mock_redis):
            resp = await integration_client.get(
                "/api/v1/auth/google/callback",
                params={"code": "auth-code", "state": "invalid-state"},
            )
        assert resp.status_code == 400

    async def test_refresh_rotates_token(self, integration_client, rsa_keys):
        """POST /auth/refresh with valid cookie returns new access token."""
        google_id = f"g-{uuid.uuid4().hex}"
        email = f"refresh-{uuid.uuid4().hex[:8]}@gmail.com"

        with _mock_google_exchange(google_id, email, "Refresh User"):
            with _mock_redis_state_valid():
                login_resp = await integration_client.get(
                    "/api/v1/auth/google/callback",
                    params={"code": "code", "state": "state"},
                )

        # Extract refresh token from Set-Cookie header
        cookies = login_resp.headers.get_list("set-cookie")
        refresh_cookie = None
        for c in cookies:
            if "refresh_token=" in c:
                refresh_cookie = c.split("refresh_token=")[1].split(";")[0]
                break

        assert refresh_cookie is not None

        # Use the refresh token
        refresh_resp = await integration_client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": refresh_cookie},
        )
        assert refresh_resp.status_code == 200
        data = refresh_resp.json()
        assert data["success"] is True
        assert "access_token" in data["data"]

    async def test_refresh_rejects_used_token(self, integration_client, rsa_keys):
        """After rotation, the old refresh token should be rejected."""
        google_id = f"g-{uuid.uuid4().hex}"
        email = f"reuse-{uuid.uuid4().hex[:8]}@gmail.com"

        with _mock_google_exchange(google_id, email, "Reuse User"):
            with _mock_redis_state_valid():
                login_resp = await integration_client.get(
                    "/api/v1/auth/google/callback",
                    params={"code": "code", "state": "state"},
                )

        cookies = login_resp.headers.get_list("set-cookie")
        refresh_cookie = None
        for c in cookies:
            if "refresh_token=" in c:
                refresh_cookie = c.split("refresh_token=")[1].split(";")[0]
                break

        # First refresh succeeds
        resp1 = await integration_client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": refresh_cookie},
        )
        assert resp1.status_code == 200

        # Second use of same token should fail (reuse detection)
        resp2 = await integration_client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": refresh_cookie},
        )
        assert resp2.status_code == 401

    async def test_logout_clears_cookie_and_revokes(self, integration_client, rsa_keys):
        """POST /auth/logout revokes token and clears cookie."""
        google_id = f"g-{uuid.uuid4().hex}"
        email = f"logout-{uuid.uuid4().hex[:8]}@gmail.com"

        with _mock_google_exchange(google_id, email, "Logout User"):
            with _mock_redis_state_valid():
                login_resp = await integration_client.get(
                    "/api/v1/auth/google/callback",
                    params={"code": "code", "state": "state"},
                )

        access_token = login_resp.json()["data"]["access_token"]

        cookies = login_resp.headers.get_list("set-cookie")
        refresh_cookie = None
        for c in cookies:
            if "refresh_token=" in c:
                refresh_cookie = c.split("refresh_token=")[1].split(";")[0]
                break

        logout_resp = await integration_client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
            cookies={"refresh_token": refresh_cookie},
        )
        assert logout_resp.status_code == 200

        # After logout, refresh should fail
        refresh_resp = await integration_client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": refresh_cookie},
        )
        assert refresh_resp.status_code == 401
