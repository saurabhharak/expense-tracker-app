import uuid

import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock

from app.auth.dependencies import get_current_user, get_current_user_optional


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_returns_user_id_from_valid_token(self, rsa_keys):
        from app.core.security import create_access_token

        user_id = uuid.uuid4()
        token = create_access_token(user_id=user_id, email="test@test.com")

        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {token}"}

        result = await get_current_user(request)
        assert result == str(user_id)

    @pytest.mark.asyncio
    async def test_raises_401_with_missing_header(self, rsa_keys):
        request = MagicMock()
        request.headers = {}

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_raises_401_with_invalid_token(self, rsa_keys):
        request = MagicMock()
        request.headers = {"Authorization": "Bearer garbage.token.here"}

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_raises_401_with_empty_bearer(self, rsa_keys):
        request = MagicMock()
        request.headers = {"Authorization": "Bearer "}

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_raises_401_with_no_bearer_prefix(self, rsa_keys):
        request = MagicMock()
        request.headers = {"Authorization": "Token some-token"}

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)
        assert exc_info.value.status_code == 401


class TestGetCurrentUserOptional:
    @pytest.mark.asyncio
    async def test_returns_user_id_when_valid(self, rsa_keys):
        from app.core.security import create_access_token

        user_id = uuid.uuid4()
        token = create_access_token(user_id=user_id)

        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {token}"}

        result = await get_current_user_optional(request)
        assert result == str(user_id)

    @pytest.mark.asyncio
    async def test_returns_none_when_no_auth(self, rsa_keys):
        request = MagicMock()
        request.headers = {}

        result = await get_current_user_optional(request)
        assert result is None
