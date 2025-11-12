"""Ranking heuristics for tutorial selection."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re
from typing import Mapping, MutableMapping, Sequence

from services.channel_defaults import default_channel_boost_map
from services.youtube import YouTubeVideo

ISO_DURATION_RE = re.compile(
    r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?",
    re.IGNORECASE,
)
SEMANTIC_KEYWORDS = [
    "tutorial",
    "course",
    "full course",
    "project",
    "end to end",
    "from scratch",
    "hands on",
    "hands-on",
    "beginner",
    "for beginners",
]
DEFAULT_CHANNEL_BOOSTS = default_channel_boost_map()
LN2 = math.log(2)
SECONDS_PER_DAY = 86400
THREE_YEARS_DAYS = 365 * 3
HALF_LIFE_AFTER_3Y_DAYS = 365 * 4
MIN_DURATION_SECONDS = 15 * 60
IDEAL_DURATION_SECONDS = 90 * 60
DURATION_SPAN_SECONDS = 70 * 60


@dataclass(frozen=True)
class RankedVideo:
    """Convenience wrapper for downstream debugging."""

    video: YouTubeVideo
    score: float


class RankingService:
    """Scores tutorials using heuristics ported from the n8n workflow."""

    def __init__(self, default_channel_boosts: Mapping[str, float] | None = None) -> None:
        self._default_channel_boosts = self._sanitize_boosts(default_channel_boosts or DEFAULT_CHANNEL_BOOSTS)

    def top_videos(
        self,
        videos: Sequence[YouTubeVideo],
        limit: int = 3,
        skill_name: str | None = None,
        user_channel_boosts: Mapping[str, float] | None = None,
    ) -> list[YouTubeVideo]:
        """Return highest-scoring videos using the custom ranking."""

        boosts: Mapping[str, float] | None = None
        if user_channel_boosts is not None:
            boosts = self._sanitize_boosts(user_channel_boosts)
        ranked: list[RankedVideo] = []
        for video in videos:
            score = self.score(video, skill_name=skill_name, user_channel_boosts=boosts)
            if score is None:
                continue
            ranked.append(RankedVideo(video=video, score=score))
        ranked.sort(key=lambda item: item.score, reverse=True)
        return [item.video for item in ranked[:limit]]

    def score(
        self,
        video: YouTubeVideo,
        *,
        skill_name: str | None = None,
        user_channel_boosts: Mapping[str, float] | None = None,
    ) -> float | None:
        """Calculate the workflow-aligned heuristic score."""

        duration_seconds = self._parse_duration_seconds(video.duration)
        duration_multiplier = self._duration_boost(duration_seconds)
        if duration_multiplier == 0:
            return None

        views = max(video.view_count or 0, 0)
        likes = max(video.like_count or 0, 0)
        comments = max(video.comment_count or 0, 0)
        like_ratio = (likes / views) if views > 0 else 0.0

        base_score = like_ratio * 10000 + views / 1000 + comments * 2
        time_multiplier = self._time_decay(video.published_at)
        semantic_multiplier = self._semantic_boost(video.title, video.description, skill_name)
        channel_multiplier = self._channel_boost(video.channel_title, user_channel_boosts)

        final_score = (
            base_score * duration_multiplier * time_multiplier * channel_multiplier * semantic_multiplier
        )
        return final_score

    def _channel_boost(
        self,
        channel_title: str | None,
        user_channel_boosts: Mapping[str, float] | None,
    ) -> float:
        name = (channel_title or "").strip().lower()
        if not name:
            return 1.0
        if user_channel_boosts is not None:
            return user_channel_boosts.get(name, 1.0)
        return self._default_channel_boosts.get(name, 1.0)

    def _semantic_boost(self, title: str | None, description: str | None, skill_name: str | None) -> float:
        text = f"{title or ''} {description or ''}".lower()
        skill_hit = bool(skill_name and skill_name.lower() in text)
        hits = 0
        phrases = 0
        for keyword in SEMANTIC_KEYWORDS:
            if " " in keyword:
                if keyword in text:
                    phrases += 1
            elif keyword in text:
                hits += 1
        vs_penalty = 0.95 if re.search(r"\bvs\b|versus|compare", text) else 1.0
        boost = (1.10 if skill_hit else 1.0)
        boost *= 1 + min(0.12, hits * 0.02)
        boost *= 1 + min(0.10, phrases * 0.05)
        return boost * vs_penalty

    def _time_decay(self, published_at: str | None) -> float:
        if not published_at:
            return 1.0
        try:
            published = self._parse_datetime(published_at)
        except ValueError:
            return 1.0
        if not published:
            return 1.0
        now = datetime.now(timezone.utc)
        delta_days = max(0, int((now - published).total_seconds() // SECONDS_PER_DAY))
        over = max(0, delta_days - THREE_YEARS_DAYS)
        if over <= 0:
            return 1.0
        return math.exp(-LN2 * (over / HALF_LIFE_AFTER_3Y_DAYS))

    def _duration_boost(self, seconds: int) -> float:
        if seconds < MIN_DURATION_SECONDS:
            return 0.0
        deviation = abs(seconds - IDEAL_DURATION_SECONDS)
        x = max(0.0, 1 - deviation / DURATION_SPAN_SECONDS)
        return 0.95 + 0.15 * x

    def _parse_duration_seconds(self, iso_duration: str | None) -> int:
        if not iso_duration:
            return 0
        match = ISO_DURATION_RE.fullmatch(iso_duration)
        if not match:
            return 0
        parts = match.groupdict(default="0")
        days = int(parts.get("days", "0") or 0)
        hours = int(parts.get("hours", "0") or 0)
        minutes = int(parts.get("minutes", "0") or 0)
        seconds = int(parts.get("seconds", "0") or 0)
        total_seconds = (
            days * 24 * 3600 +
            hours * 3600 +
            minutes * 60 +
            seconds
        )
        return total_seconds

    def _parse_datetime(self, value: str) -> datetime | None:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(f"Invalid datetime string: {value}") from exc
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def _sanitize_boosts(self, boosts: Mapping[str, float] | None) -> dict[str, float]:
        sanitized: MutableMapping[str, float] = {}
        if not boosts:
            return {}
        for name, value in boosts.items():
            if not name:
                continue
            try:
                multiplier = float(value)
            except (TypeError, ValueError):
                continue
            if multiplier <= 0:
                continue
            sanitized[name.strip().lower()] = multiplier
        return dict(sanitized)
