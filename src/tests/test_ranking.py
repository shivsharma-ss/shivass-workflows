"""Ranking heuristics tests for YouTube video scoring."""

from services.ranking import RankingService
from services.youtube import YouTubeVideo


def test_ranking_prefers_high_views():
    """High engagement videos should outrank low-signal entries."""
    ranking = RankingService()
    low = YouTubeVideo(
        video_id="1",
        title="Low",
        description="",
        url="https://youtu.be/1",
        channel_title="A",
        duration="PT20M",
        view_count=100,
        like_count=10,
        comment_count=0,
        published_at="2023-01-01T00:00:00Z",
    )
    high = YouTubeVideo(
        video_id="2",
        title="High",
        description="",
        url="https://youtu.be/2",
        channel_title="B",
        duration="PT95M",
        view_count=50000,
        like_count=5000,
        comment_count=200,
        published_at="2024-01-01T00:00:00Z",
    )
    ranked = ranking.top_videos([low, high], limit=1)
    assert ranked[0].video_id == "2"


def test_ranking_filters_short_videos():
    """Videos shorter than 15 minutes should be filtered out."""
    ranking = RankingService()
    short = YouTubeVideo(
        video_id="1",
        title="Short",
        description="",
        url="https://youtu.be/1",
        channel_title="A",
        duration="PT10M",
        view_count=10000,
        like_count=1000,
    )
    long = YouTubeVideo(
        video_id="2",
        title="Long",
        description="",
        url="https://youtu.be/2",
        channel_title="B",
        duration="PT30M",
        view_count=10,
        like_count=1,
    )
    ranked = ranking.top_videos([short, long], limit=2)
    assert len(ranked) == 1
    assert ranked[0].video_id == "2"


def test_ranking_semantic_skill_boost():
    """Semantic hits and skill matches should gently boost results."""
    ranking = RankingService()
    generic = YouTubeVideo(
        video_id="1",
        title="Python tips",
        description="Assorted thoughts",
        url="https://youtu.be/1",
        channel_title="A",
        duration="PT45M",
        view_count=1000,
        like_count=100,
    )
    targeted = YouTubeVideo(
        video_id="2",
        title="Python tutorial for beginners",
        description="From scratch hands-on course",
        url="https://youtu.be/2",
        channel_title="B",
        duration="PT60M",
        view_count=1000,
        like_count=100,
    )
    ranked = ranking.top_videos([generic, targeted], limit=1, skill_name="Python")
    assert ranked[0].video_id == "2"


def test_ranking_applies_user_channel_boost():
    """User-defined boosts should override defaults."""
    ranking = RankingService(default_channel_boosts={"channel a": 1.0, "channel b": 1.0})
    a = YouTubeVideo(
        video_id="1",
        title="Tutorial A",
        description="",
        url="https://youtu.be/1",
        channel_title="Channel A",
        duration="PT40M",
        view_count=1000,
        like_count=100,
    )
    b = YouTubeVideo(
        video_id="2",
        title="Tutorial B",
        description="",
        url="https://youtu.be/2",
        channel_title="Channel B",
        duration="PT40M",
        view_count=1000,
        like_count=100,
    )
    ranked = ranking.top_videos(
        [a, b],
        limit=1,
        user_channel_boosts={"channel b": 1.5},
    )
    assert ranked[0].video_id == "2"
