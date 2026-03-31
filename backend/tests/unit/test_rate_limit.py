import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.rate_limit import check_rate_limit


class TestCheckRateLimit:
    @pytest.mark.asyncio
    async def test_allows_request_under_limit(self):
        mock_redis = MagicMock()
        mock_redis.zadd = AsyncMock()
        mock_redis.expire = AsyncMock()
        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [None, 1]  # [zremrangebyscore, zcard=1]
        mock_redis.pipeline.return_value = mock_pipe

        allowed = await check_rate_limit(mock_redis, "test:key", limit=3, window_seconds=600)
        assert allowed is True
        # Should add timestamp since request is allowed
        mock_redis.zadd.assert_called_once()

    @pytest.mark.asyncio
    async def test_blocks_request_over_limit(self):
        mock_redis = MagicMock()
        mock_redis.zadd = AsyncMock()
        mock_redis.expire = AsyncMock()
        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [None, 4]  # count=4 > limit=3
        mock_redis.pipeline.return_value = mock_pipe

        allowed = await check_rate_limit(mock_redis, "test:key", limit=3, window_seconds=600)
        assert allowed is False
        # Should NOT add timestamp for denied requests
        mock_redis.zadd.assert_not_called()

    @pytest.mark.asyncio
    async def test_blocks_at_exact_limit(self):
        mock_redis = MagicMock()
        mock_redis.zadd = AsyncMock()
        mock_redis.expire = AsyncMock()
        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [None, 3]  # count=3, limit=3
        mock_redis.pipeline.return_value = mock_pipe

        allowed = await check_rate_limit(mock_redis, "test:key", limit=3, window_seconds=600)
        assert allowed is False
        mock_redis.zadd.assert_not_called()

    @pytest.mark.asyncio
    async def test_allows_just_under_limit(self):
        mock_redis = MagicMock()
        mock_redis.zadd = AsyncMock()
        mock_redis.expire = AsyncMock()
        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [None, 2]  # count=2, limit=3
        mock_redis.pipeline.return_value = mock_pipe

        allowed = await check_rate_limit(mock_redis, "test:key", limit=3, window_seconds=600)
        assert allowed is True
        mock_redis.zadd.assert_called_once()

    @pytest.mark.asyncio
    async def test_pipeline_prune_and_count(self):
        mock_redis = MagicMock()
        mock_redis.zadd = AsyncMock()
        mock_redis.expire = AsyncMock()
        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [None, 1]
        mock_redis.pipeline.return_value = mock_pipe

        await check_rate_limit(mock_redis, "rate:otp:+919876543210", limit=3, window_seconds=600)

        mock_pipe.zremrangebyscore.assert_called_once()
        mock_pipe.zcard.assert_called_once()
