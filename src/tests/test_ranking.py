"""Ranking heuristics tests for YouTube video scoring."""

from services.ranking import RankingService
from services.youtube import YouTubeVideo


def test_ranking_prefers_high_views():
    """High view/like counts should outrank low engagement tutorials."""
    ranking = RankingService()
    low = YouTubeVideo(
        video_id="1",
        title="Low",
        description="",
        url="https://youtu.be/1",
        channel_title="A",
        duration="PT50M",
        view_count=100,
        like_count=10,
    )
    high = YouTubeVideo(
        video_id="2",
        title="High",
        description="",
        url="https://youtu.be/2",
        channel_title="B",
        duration="PT15M",
        view_count=50000,
        like_count=5000,
    )
    ranked = ranking.top_videos([low, high], limit=1)
    assert ranked[0].video_id == "2"
