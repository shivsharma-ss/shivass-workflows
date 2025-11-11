"""Ranking heuristics for tutorial selection."""
from __future__ import annotations

import math
from typing import Sequence

from services.youtube import YouTubeVideo


class RankingService:
    """Scores tutorials using lightweight heuristics."""

    def score(self, video: YouTubeVideo) -> float:
        """Combine log views, likes, and duration preference."""

        views = math.log(max(video.view_count or 1, 1), 10)
        likes = math.log(max(video.like_count or 1, 1), 10)
        duration_penalty = 0.0
        if video.duration:
            # ISO 8601 durations like PT15M20S
            minutes = self._duration_to_minutes(video.duration)
            if minutes > 40:
                duration_penalty = 0.5
        return views * 0.7 + likes * 0.3 - duration_penalty

    def top_videos(self, videos: Sequence[YouTubeVideo], limit: int = 3) -> list[YouTubeVideo]:
        """Return the highest-scoring tutorials."""

        scored = sorted(videos, key=self.score, reverse=True)
        return list(scored[:limit])

    def _duration_to_minutes(self, iso_duration: str) -> float:
        total_minutes = 0.0
        current = ""
        value = 0
        for ch in iso_duration:
            if ch.isdigit():
                current += ch
            elif ch == "H":
                value = int(current or 0)
                total_minutes += value * 60
                current = ""
            elif ch == "M":
                value = int(current or 0)
                total_minutes += value
                current = ""
            elif ch == "S":
                current = ""
        return total_minutes
