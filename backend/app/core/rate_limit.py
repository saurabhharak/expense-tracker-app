"""Redis sliding-window rate limiter using sorted sets."""

import time

from redis.asyncio import Redis


async def check_rate_limit(redis: Redis, key: str, limit: int, window_seconds: int) -> bool:
    """Check if a request is within the rate limit.

    Uses a Redis sorted set where each entry is a timestamp.
    Entries outside the window are pruned on each check.
    Only adds a timestamp when the request is allowed (denied requests
    don't consume rate-limit slots).

    Args:
        redis: Async Redis client.
        key: Rate limit key (e.g. "otp_send:+919876543210").
        limit: Maximum allowed requests in the window.
        window_seconds: Sliding window duration in seconds.

    Returns:
        True if request is allowed, False if rate limited.
    """
    now = time.time()

    # Step 1: Prune expired entries and count current window
    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, now - window_seconds)
    pipe.zcard(key)
    results = await pipe.execute()
    count = results[1]

    if count >= limit:
        return False

    # Step 2: Only add timestamp when allowing the request
    await redis.zadd(key, {f"{now}": now})
    await redis.expire(key, window_seconds)
    return True
