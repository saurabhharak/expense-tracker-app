import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.auth.oauth import GoogleUserInfo
from app.auth.service import find_or_create_google_user, issue_token_pair, rotate_refresh_token, revoke_refresh_token


class TestFindOrCreateGoogleUser:
    @pytest.mark.asyncio
    async def test_returns_existing_user_by_google_id(self):
        """If a user with this google_id exists, return them."""
        existing_user = MagicMock()
        existing_user.id = uuid.uuid4()
        existing_user.email = "user@gmail.com"
        existing_user.google_id = "g-123"
        existing_user.is_active = True

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_user
        mock_session.execute.return_value = mock_result

        google_info = GoogleUserInfo(
            google_id="g-123",
            email="user@gmail.com",
            email_verified=True,
            full_name="Test User",
            avatar_url=None,
        )

        user, created = await find_or_create_google_user(mock_session, google_info)
        assert user.id == existing_user.id
        assert created is False

    @pytest.mark.asyncio
    async def test_creates_new_user_when_not_found(self):
        """If no user with this google_id exists, create one."""
        mock_session = AsyncMock()
        # First query (by google_id) returns None
        mock_result_1 = MagicMock()
        mock_result_1.scalar_one_or_none.return_value = None
        # Second query (by email) returns None
        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = None
        mock_session.execute.side_effect = [mock_result_1, mock_result_2]

        google_info = GoogleUserInfo(
            google_id="g-new",
            email="new@gmail.com",
            email_verified=True,
            full_name="New User",
            avatar_url="https://photo.jpg",
        )

        user, created = await find_or_create_google_user(mock_session, google_info)
        assert created is True
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_links_google_to_existing_email_user(self):
        """If a user with matching email exists but no google_id, link them."""
        existing_user = MagicMock()
        existing_user.id = uuid.uuid4()
        existing_user.email = "user@gmail.com"
        existing_user.google_id = None
        existing_user.is_active = True
        existing_user.avatar_url = None

        mock_session = AsyncMock()
        # First query (by google_id) returns None
        mock_result_1 = MagicMock()
        mock_result_1.scalar_one_or_none.return_value = None
        # Second query (by email) returns existing user
        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = existing_user
        mock_session.execute.side_effect = [mock_result_1, mock_result_2]

        google_info = GoogleUserInfo(
            google_id="g-link",
            email="user@gmail.com",
            email_verified=True,
            full_name="User",
            avatar_url=None,
        )

        user, created = await find_or_create_google_user(mock_session, google_info)
        assert created is False
        assert user.google_id == "g-link"

    @pytest.mark.asyncio
    async def test_raises_on_deactivated_user(self):
        """Deactivated user should raise ValueError."""
        existing_user = MagicMock()
        existing_user.is_active = False
        existing_user.google_id = "g-deactivated"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_user
        mock_session.execute.return_value = mock_result

        google_info = GoogleUserInfo(
            google_id="g-deactivated",
            email="deactivated@gmail.com",
            email_verified=True,
            full_name="Deactivated User",
            avatar_url=None,
        )

        with pytest.raises(ValueError, match="deactivated"):
            await find_or_create_google_user(mock_session, google_info)


class TestIssueTokenPair:
    @pytest.mark.asyncio
    async def test_returns_access_token_and_raw_refresh_token(self, rsa_keys):
        user = MagicMock()
        user.id = uuid.uuid4()
        user.email = "user@test.com"

        mock_session = AsyncMock()

        access_token, refresh_token_raw = await issue_token_pair(
            session=mock_session,
            user=user,
            user_agent="TestAgent",
            ip_address="127.0.0.1",
        )

        assert isinstance(access_token, str)
        assert len(access_token) > 0
        assert isinstance(refresh_token_raw, str)
        assert len(refresh_token_raw) == 64  # 32 bytes hex
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()


class TestRotateRefreshToken:
    @pytest.mark.asyncio
    async def test_revokes_old_and_issues_new(self, rsa_keys):
        old_token_record = MagicMock()
        old_token_record.id = uuid.uuid4()
        old_token_record.user_id = uuid.uuid4()
        old_token_record.revoked_at = None
        old_token_record.expires_at = datetime.now(timezone.utc) + timedelta(days=10)

        user = MagicMock()
        user.id = old_token_record.user_id
        user.email = "user@test.com"
        user.is_active = True

        mock_session = AsyncMock()
        # Query for old token by hash
        mock_result_token = MagicMock()
        mock_result_token.scalar_one_or_none.return_value = old_token_record
        # Query for user
        mock_result_user = MagicMock()
        mock_result_user.scalar_one_or_none.return_value = user
        # Query for new token record (after issue_token_pair flushes)
        mock_result_new_token = MagicMock()
        new_token_record = MagicMock()
        new_token_record.id = uuid.uuid4()
        mock_result_new_token.scalar_one_or_none.return_value = new_token_record
        mock_session.execute.side_effect = [mock_result_token, mock_result_user, mock_result_new_token]

        access_token, new_refresh_raw = await rotate_refresh_token(
            session=mock_session,
            old_token_raw="a" * 64,
            user_agent="TestAgent",
            ip_address="127.0.0.1",
        )

        assert old_token_record.revoked_at is not None
        assert isinstance(access_token, str)
        assert isinstance(new_refresh_raw, str)

    @pytest.mark.asyncio
    async def test_raises_on_revoked_token_reuse(self, rsa_keys):
        """Reuse of a revoked token should raise and revoke the family."""
        revoked_token = MagicMock()
        revoked_token.id = uuid.uuid4()
        revoked_token.user_id = uuid.uuid4()
        revoked_token.revoked_at = datetime.now(timezone.utc)  # already revoked
        revoked_token.expires_at = datetime.now(timezone.utc) + timedelta(days=10)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = revoked_token
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="reuse detected"):
            await rotate_refresh_token(
                session=mock_session,
                old_token_raw="a" * 64,
                user_agent="TestAgent",
                ip_address="127.0.0.1",
            )

    @pytest.mark.asyncio
    async def test_raises_on_expired_token(self, rsa_keys):
        expired_token = MagicMock()
        expired_token.id = uuid.uuid4()
        expired_token.user_id = uuid.uuid4()
        expired_token.revoked_at = None
        expired_token.expires_at = datetime.now(timezone.utc) - timedelta(days=1)  # expired

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expired_token
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="expired"):
            await rotate_refresh_token(
                session=mock_session,
                old_token_raw="a" * 64,
                user_agent="TestAgent",
                ip_address="127.0.0.1",
            )

    @pytest.mark.asyncio
    async def test_raises_on_not_found(self, rsa_keys):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="not found"):
            await rotate_refresh_token(
                session=mock_session,
                old_token_raw="nonexistent" * 4,
                user_agent="TestAgent",
                ip_address="127.0.0.1",
            )


class TestRevokeRefreshToken:
    @pytest.mark.asyncio
    async def test_revokes_active_token(self):
        token_record = MagicMock()
        token_record.revoked_at = None

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = token_record
        mock_session.execute.return_value = mock_result

        await revoke_refresh_token(mock_session, "a" * 64)
        assert token_record.revoked_at is not None

    @pytest.mark.asyncio
    async def test_noop_for_missing_token(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Should not raise
        await revoke_refresh_token(mock_session, "nonexistent" * 4)
