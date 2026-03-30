import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.rate_limit import check_rate_limit


class TestCheckRateLimit:
    @pytest.mark.asyncio
    async def test_allows_request_under_limit(self):
        mock_redis = MagicMock()
        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [None, None, 1, None]
        mock_redis.pipeline.return_value = mock_pipe

        allowed = await check_rate_limit(mock_redis, "test:key", limit=3, window_seconds=600)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_blocks_request_over_limit(self):
        mock_redis = MagicMock()
        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [None, None, 4, None]
        mock_redis.pipeline.return_value = mock_pipe

        allowed = await check_rate_limit(mock_redis, "test:key", limit=3, window_seconds=600)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_allows_at_exact_limit(self):
        mock_redis = MagicMock()
        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [None, None, 3, None]
        mock_redis.pipeline.return_value = mock_pipe

        allowed = await check_rate_limit(mock_redis, "test:key", limit=3, window_seconds=600)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_pipeline_operations_called(self):
        mock_redis = MagicMock()
        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [None, None, 1, None]
        mock_redis.pipeline.return_value = mock_pipe

        await check_rate_limit(mock_redis, "rate:otp:+919876543210", limit=3, window_seconds=600)

        mock_pipe.zremrangebyscore.assert_called_once()
        mock_pipe.zadd.assert_called_once()
        mock_pipe.zcard.assert_called_once()
        mock_pipe.expire.assert_called_once()
