import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.auth.service import find_or_create_phone_user


class TestFindOrCreatePhoneUser:
    @pytest.mark.asyncio
    async def test_returns_existing_user_by_phone(self):
        existing_user = MagicMock()
        existing_user.id = uuid.uuid4()
        existing_user.phone = "+919876543210"
        existing_user.is_active = True

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_user
        mock_session.execute.return_value = mock_result

        user, created = await find_or_create_phone_user(mock_session, "+919876543210")
        assert user.id == existing_user.id
        assert created is False

    @pytest.mark.asyncio
    async def test_creates_new_user_when_not_found(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        user, created = await find_or_create_phone_user(mock_session, "+919876543210")
        assert created is True
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_on_deactivated_user(self):
        existing_user = MagicMock()
        existing_user.is_active = False
        existing_user.phone = "+919876543210"

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_user
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="deactivated"):
            await find_or_create_phone_user(mock_session, "+919876543210")
