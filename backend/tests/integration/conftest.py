"""Integration test configuration.

Integration tests use a shared event loop (session-scoped) to avoid asyncpg
connection pool issues caused by per-test event loop teardown.
"""

import asyncio

import pytest


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use the default event loop policy for all integration tests."""
    return asyncio.DefaultEventLoopPolicy()
