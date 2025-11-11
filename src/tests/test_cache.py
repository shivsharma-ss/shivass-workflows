"""CacheService unit tests covering memory fallback behavior."""

import pytest

from services.cache import CacheService


@pytest.mark.asyncio
async def test_cache_round_trip_and_expiry(monkeypatch):
    """Ensure values expire immediately when ttl=0 and persist otherwise."""
    cache = CacheService(redis_url=None)
    assert await cache.get("missing") is None

    await cache.set("key", {"value": 1}, ttl_seconds=0)
    assert await cache.get("key") is None

    await cache.set("fresh", {"value": 2}, ttl_seconds=5)
    assert await cache.get("fresh") == {"value": 2}


@pytest.mark.asyncio
async def test_video_analysis_helpers():
    """Helper methods should reuse the common cache surface."""
    cache = CacheService(redis_url=None)
    payload = {"summary": "Test"}
    url = "https://youtu.be/abc"
    await cache.set_video_analysis(url, payload, ttl_seconds=5)
    assert await cache.get_video_analysis(url) == payload
