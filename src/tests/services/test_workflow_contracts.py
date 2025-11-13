"""Service-level integration tests tying schemas + ranking together."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.schemas import AnalysisRequest, PreferredChannelBoost
from services.channel_defaults import default_channel_boost_map
from services.ranking import RankingService
from services.storage import StorageService
from services.youtube import YouTubeVideo


@pytest.mark.asyncio
async def test_analysis_request_round_trip_and_ranking_defaults(tmp_path):
    preferred = next(iter(default_channel_boost_map().keys()))
    request = AnalysisRequest(
        email="user@example.com",
        cvDocId="doc123",
        jobDescription="Build dashboards",
        jobDescriptionUrl=None,
        preferredYoutubeChannels=[PreferredChannelBoost(name=preferred, boost=1.2)],
    )
    serialized = request.model_dump(by_alias=True)
    round_trip = AnalysisRequest.model_validate(serialized)
    assert round_trip.model_dump() == request.model_dump()

    ranking = RankingService()
    base_video = {
        "video_id": "vid",
        "description": "tutorial",
        "url": "https://youtu.be/vid",
        "duration": "PT45M",
        "view_count": 5000,
        "like_count": 500,
        "comment_count": 25,
        "published_at": datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat(),
    }
    boosted = ranking.score(
        YouTubeVideo(title="Best tutorial", channel_title=preferred, **base_video)
    )
    neutral = ranking.score(
        YouTubeVideo(title="Best tutorial", channel_title="random channel", **base_video)
    )
    assert boosted is not None and neutral is not None
    assert boosted > neutral

    storage = StorageService(f"sqlite+aiosqlite:///{tmp_path / 'runs.db'}")
    await storage.initialize()
    await storage.create_analysis("run-1", request.email, request.cvDocId, request.model_dump())
    saved = await storage.get_analysis("run-1")
    assert saved is not None
    assert saved.payload["preferredYoutubeChannels"][0]["name"] == preferred
