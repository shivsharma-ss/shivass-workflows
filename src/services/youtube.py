"""YouTube Data API helpers with quota tracking."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from services.cache import CacheService
from services.storage import StorageService

YT_BASE = "https://www.googleapis.com/youtube/v3"
SEARCH_COST = 100
VIDEOS_COST = 1

logger = logging.getLogger(__name__)


@dataclass
class YouTubeVideo:
    video_id: str
    title: str
    description: str
    url: str
    channel_title: str
    duration: Optional[str]
    view_count: Optional[int]
    like_count: Optional[int]


class YouTubeService:
    """Quota-aware YouTube client with caching."""

    def __init__(
        self,
        api_key: str,
        cache: CacheService,
        storage: Optional[StorageService],
        daily_quota: int,
    ) -> None:
        self._api_key = api_key
        self._cache = cache
        self._storage = storage
        self._daily_quota = daily_quota
        self._quota_used = 0

    @property
    def quota_remaining(self) -> int:
        """Return the remaining daily quota budget."""

        return max(self._daily_quota - self._quota_used, 0)

    async def search_tutorials(self, query: str, max_results: int = 10) -> list[YouTubeVideo]:
        """Search and enrich videos for a query."""

        cache_key = f"yt:{query}:{max_results}"
        cached = await self._cache.get(cache_key)
        if cached:
            logger.debug("YouTube cache hit (memory) for query '%s'", query)
            return [YouTubeVideo(**item) for item in cached]

        persisted = await self._load_persisted(query)
        if persisted:
            logger.info("YouTube cache hit (db) for query '%s'", query)
            await self._cache.set(cache_key, persisted, ttl_seconds=3600)
            return [YouTubeVideo(**item) for item in persisted]

        logger.info("YouTube search for '%s' (quota remaining=%s)", query, self.quota_remaining)
        search_items = await self._search(query=query, max_results=max_results)
        video_ids = [item["id"]["videoId"] for item in search_items if item.get("id", {}).get("videoId")]
        stats = await self._videos(video_ids)
        stats_map = {item["id"]: item for item in stats}
        videos: list[YouTubeVideo] = []
        for item in search_items:
            vid = item.get("id", {}).get("videoId")
            snippet = item.get("snippet", {})
            stat_entry = stats_map.get(vid, {})
            videos.append(
                YouTubeVideo(
                    video_id=vid or "",
                    title=snippet.get("title", ""),
                    description=snippet.get("description", ""),
                    url=f"https://youtu.be/{vid}" if vid else "",
                    channel_title=snippet.get("channelTitle", ""),
                    duration=stat_entry.get("contentDetails", {}).get("duration"),
                    view_count=int(stat_entry.get("statistics", {}).get("viewCount", 0) or 0),
                    like_count=int(stat_entry.get("statistics", {}).get("likeCount", 0) or 0),
                )
            )
        payload = [video.__dict__ for video in videos]
        await self._cache.set(cache_key, payload, ttl_seconds=3600)
        await self._persist(query, payload)
        return videos

    async def _load_persisted(self, query: str) -> Optional[list[dict[str, Any]]]:
        if not self._storage:
            return None
        return await self._storage.get_youtube_cache(query)

    async def _persist(self, query: str, payload: list[dict[str, Any]]) -> None:
        if not self._storage:
            return
        await self._storage.save_youtube_cache(query, payload)
        for video in payload:
            video_url = video.get("url", "")
            if not video_url:
                continue
            try:
                await self._storage.save_youtube_video_metadata(
                    video_url=video_url,
                    summary=video.get("description"),
                    skills=None,
                    tech_stack=None,
                )
            except Exception:
                logger.exception("Failed to persist video metadata for %s", video.get("url"))

    async def _search(self, query: str, max_results: int) -> list[dict[str, Any]]:
        self._consume_quota(SEARCH_COST)
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": "relevance",
            "maxResults": max_results,
            "key": self._api_key,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{YT_BASE}/search", params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("items", [])

    async def _videos(self, video_ids: list[str]) -> list[dict[str, Any]]:
        if not video_ids:
            return []
        self._consume_quota(VIDEOS_COST)
        params = {
            "part": "statistics,contentDetails",
            "id": ",".join(video_ids),
            "key": self._api_key,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{YT_BASE}/videos", params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("items", [])

    def _consume_quota(self, cost: int) -> None:
        if self._quota_used + cost > self._daily_quota:
            raise RuntimeError("YouTube quota exceeded for the day")
        self._quota_used += cost
