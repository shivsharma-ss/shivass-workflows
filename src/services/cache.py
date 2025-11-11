"""TTL cache with optional Redis backend."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

try:
    from redis import asyncio as redis_asyncio
except ImportError:  # pragma: no cover - redis optional
    redis_asyncio = None  # type: ignore


@dataclass
class CacheEntry:
    value: Any
    expires_at: datetime


class CacheService:
    """A very small cache facade that prefers Redis but falls back to memory."""

    def __init__(self, redis_url: Optional[str]):
        self._redis = None
        if redis_url and redis_asyncio:
            try:
                self._redis = redis_asyncio.from_url(redis_url)
            except Exception:
                self._redis = None
        self._store: dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any:
        """Return a cached value or None."""

        if self._redis:
            try:
                result = await self._redis.get(key)
                return json.loads(result) if result else None
            except Exception:
                pass
        async with self._lock:
            entry = self._store.get(key)
            if entry and entry.expires_at > datetime.now(timezone.utc):
                return entry.value
            if entry:
                self._store.pop(key, None)
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        """Store a value for a period of time."""

        expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        if self._redis:
            try:
                await self._redis.set(key, json.dumps(value), ex=ttl_seconds)
                return
            except Exception:
                pass
        async with self._lock:
            self._store[key] = CacheEntry(value=value, expires_at=expires)

    async def get_video_analysis(self, url: str) -> Optional[dict[str, Any]]:
        """Return a cached Gemini analysis for a video URL."""

        if not url:
            return None
        key = f"gemini:video:{url}"
        return await self.get(key)

    async def set_video_analysis(self, url: str, analysis: dict[str, Any], ttl_seconds: int = 86400) -> None:
        """Cache Gemini video analysis payloads for a full day."""

        if not url:
            return
        key = f"gemini:video:{url}"
        await self.set(key, analysis, ttl_seconds=ttl_seconds)
