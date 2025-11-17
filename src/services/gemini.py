"""Gemini-powered video analysis helpers."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, List, Optional

from google import genai
from google.genai import types

from services.cache import CacheService
from services.storage import StorageService

logger = logging.getLogger(__name__)


def _as_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


@dataclass
class VideoAnalysis:
    """Structured Gemini output for a single tutorial."""

    summary: str
    key_points: List[str]
    difficulty_level: str
    prerequisites: List[str]
    practical_takeaways: List[str]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "VideoAnalysis":
        return cls(
            summary=str(payload.get("summary", "")).strip(),
            key_points=_as_list(payload.get("key_points") or payload.get("keyPoints")),
            difficulty_level=str(payload.get("difficulty_level") or payload.get("difficultyLevel") or "").strip(),
            prerequisites=_as_list(payload.get("prerequisites")),
            practical_takeaways=_as_list(payload.get("practical_takeaways") or payload.get("practicalTakeaways")),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "key_points": self.key_points,
            "difficulty_level": self.difficulty_level,
            "prerequisites": self.prerequisites,
            "practical_takeaways": self.practical_takeaways,
        }


class GeminiService:
    """Wrapper around the google-genai SDK with caching + retries."""

    def __init__(
        self,
        api_key: str,
        cache: Optional[CacheService] = None,
        storage: Optional[StorageService] = None,
        model: str = "gemini-2.5-flash",
        client: Optional[genai.Client] = None,
    ) -> None:
        self._cache = cache
        self._storage = storage
        self._model = model
        self._client = client or genai.Client(api_key=api_key)

    async def analyze_video(self, url: str) -> Optional[VideoAnalysis]:
        """Analyze a YouTube tutorial URL and return structured insights."""

        if not url:
            return None
        try:
            cached = await self._fetch_cached(url)
            if cached:
                return cached
            analysis = await self._analyze_with_retries(url)
            if analysis:
                await self._cache_result(url, analysis)
            return analysis
        except Exception:
            logger.exception("Gemini analysis failed for %s", url)
            return None

    async def _fetch_cached(self, url: str) -> Optional[VideoAnalysis]:
        cached_payload: Optional[dict[str, Any]] = None
        if self._cache:
            cached_payload = await self._cache.get_video_analysis(url)
        if cached_payload:
            try:
                return VideoAnalysis.from_payload(cached_payload)
            except Exception:
                logger.warning("Corrupt Gemini cache entry for %s", url, exc_info=True)
        if not self._storage:
            return None
        persisted = await self._storage.get_youtube_video_metadata(url)
        if not _has_structured_analysis(persisted):
            return None
        payload = {
            "summary": persisted.get("summary", ""),
            "key_points": persisted.get("key_points", []),
            "difficulty_level": persisted.get("difficulty_level", ""),
            "prerequisites": persisted.get("prerequisites", []),
            "practical_takeaways": persisted.get("takeaways", []),
        }
        analysis = VideoAnalysis.from_payload(payload)
        if self._cache:
            await self._cache.set_video_analysis(url, analysis.to_payload())
        return analysis

    async def _cache_result(self, url: str, analysis: VideoAnalysis) -> None:
        if self._cache:
            await self._cache.set_video_analysis(url, analysis.to_payload())
        if self._storage:
            try:
                await self._storage.save_youtube_video_metadata(
                    video_url=url,
                    summary=analysis.summary,
                    key_points=analysis.key_points,
                    difficulty_level=analysis.difficulty_level,
                    prerequisites=analysis.prerequisites,
                    takeaways=analysis.practical_takeaways,
                )
            except Exception:
                logger.warning("Failed to persist Gemini analysis for %s", url, exc_info=True)

    async def _analyze_with_retries(self, url: str, max_retries: int = 3) -> Optional[VideoAnalysis]:
        delay = 1
        for attempt in range(max_retries):
            try:
                return await self._perform_analysis(url)
            except Exception:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(delay)
                delay *= 2
        return None

    async def _perform_analysis(self, url: str) -> VideoAnalysis:
        prompt = (
            "Analyze this YouTube tutorial and return JSON with keys: summary, key_points,"
            " difficulty_level, prerequisites, practical_takeaways. URL: "
            f"{url}"
        )

        def _call():
            return self._client.models.generate_content(
                model=self._model,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    response_mime_type="application/json",
                ),
            )

        response = await asyncio.to_thread(_call)
        payload = self._extract_json(response)
        return VideoAnalysis.from_payload(payload)

    def _extract_json(self, response: Any) -> dict[str, Any]:
        if getattr(response, "parsed", None):
            parsed = response.parsed
            if isinstance(parsed, list):
                parsed = parsed[0]
            if isinstance(parsed, dict):
                return parsed
        text = getattr(response, "text", None) or getattr(response, "output_text", None)
        if not text and getattr(response, "candidates", None):
            texts: list[str] = []
            for candidate in response.candidates:
                parts = getattr(candidate, "content", getattr(candidate, "contents", None))
                part_list = getattr(parts, "parts", None) if parts else None
                iterable = part_list or []
                for part in iterable:
                    if hasattr(part, "text"):
                        texts.append(part.text)
            text = "\n".join(texts).strip() if texts else None
        if not text:
            raise ValueError("Gemini response did not include text output")
        return json.loads(text)


def _has_structured_analysis(metadata: Optional[dict[str, Any]]) -> bool:
    if not metadata:
        return False
    return bool(
        metadata.get("key_points")
        or metadata.get("prerequisites")
        or metadata.get("takeaways")
        or metadata.get("difficulty_level")
    )
