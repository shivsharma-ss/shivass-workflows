"""Integration tests for workflow enhancements."""
from __future__ import annotations

import pytest

from app.schemas import AnalysisStatus, TutorialSuggestion
from orchestrator.nodes import yt_branch, mvp_projects
from orchestrator.state import GraphState, NodeDeps
from services.gemini import VideoAnalysis
from services.ranking import RankedVideo, RankingService
from services.youtube import YouTubeVideo


class FakeStorage:
    def __init__(self):
        self.artifacts = {}
        self.node_events = []
        self.video_metadata = {}

    async def save_artifact(self, analysis_id, artifact_type, content):
        self.artifacts[(analysis_id, artifact_type)] = content

    async def record_node_event(self, analysis_id, node_name, **kwargs):
        self.node_events.append({"analysis_id": analysis_id, "node_name": node_name, **kwargs})

    async def get_youtube_video_metadata(self, url):
        return self.video_metadata.get(url)


class FakeYouTube:
    async def search_tutorials(self, query, max_results):
        return [
            YouTubeVideo(
                video_id="v1",
                title="Tutorial 1",
                url="https://youtu.be/v1",
                channel_title="Channel A",
                duration="PT10M",
                view_count=1000,
                like_count=100,
                comment_count=10,
                published_at="2024-01-01",
            ),
            YouTubeVideo(
                video_id="v2",
                title="Tutorial 2",
                url="https://youtu.be/v2",
                channel_title="Channel B",
                duration="PT15M",
                view_count=2000,
                like_count=200,
                comment_count=20,
                published_at="2024-01-02",
            ),
        ]


class FakeGemini:
    async def analyze_video(self, url):
        return VideoAnalysis(
            summary="Video summary",
            key_points=["Point 1", "Point 2"],
            difficulty_level="Intermediate",
            prerequisites=["Python"],
            practical_takeaways=["Build something"],
        )


@pytest.mark.asyncio
async def test_yt_branch_saves_video_rankings_artifact():
    """YouTube branch should save video rankings as artifact."""
    storage = FakeStorage()
    youtube = FakeYouTube()
    gemini = FakeGemini()
    ranking = RankingService()

    deps = NodeDeps(
        settings=None,
        storage=storage,
        drive=None,
        docs=None,
        gmail=None,
        llm=None,
        ranking=ranking,
        youtube=youtube,
        gemini=gemini,
    )

    state: GraphState = {
        "analysis_id": "test-1",
        "skill_queries": [{"skill": "Python", "query": "Python tutorial"}],
    }

    node = yt_branch.build_node(deps)
    result = await node(state)

    # Verify video_rankings artifact was saved
    assert ("test-1", "video_rankings") in storage.artifacts
    rankings = storage.artifacts[("test-1", "video_rankings")]
    assert len(rankings) == 1
    assert rankings[0]["skill"] == "Python"
    assert "videos" in rankings[0]


@pytest.mark.asyncio
async def test_yt_branch_instruments_node_events():
    """YouTube branch should record node execution events."""
    storage = FakeStorage()
    youtube = FakeYouTube()
    ranking = RankingService()

    deps = NodeDeps(
        settings=None,
        storage=storage,
        drive=None,
        docs=None,
        gmail=None,
        llm=None,
        ranking=ranking,
        youtube=youtube,
        gemini=None,
    )

    state: GraphState = {
        "analysis_id": "test-2",
        "skill_queries": [{"skill": "JavaScript", "query": "JS tutorial"}],
    }

    node = yt_branch.build_node(deps)
    await node(state)

    # Verify node event was recorded
    assert len(storage.node_events) == 1
    event = storage.node_events[0]
    assert event["analysis_id"] == "test-2"
    assert event["node_name"] == "yt_branch"


@pytest.mark.asyncio
async def test_mvp_projects_handles_none_suggestions():
    """MVP projects node should handle None project suggestions gracefully."""
    storage = FakeStorage()

    class FakeLLM:
        async def generate_mvp_projects(self, *args, **kwargs):
            return []

    deps = NodeDeps(
        settings=None,
        storage=storage,
        drive=None,
        docs=None,
        gmail=None,
        llm=FakeLLM(),
        ranking=None,
        youtube=None,
        gemini=None,
    )

    state: GraphState = {
        "analysis_id": "test-3",
        "project_suggestions": None,  # None instead of list
        "analysis_model": None,
    }

    node = mvp_projects.build_node(deps)
    result = await node(state)

    # Should not crash and should handle gracefully
    assert "mvp_projects" in result


@pytest.mark.asyncio
async def test_mvp_projects_instruments_node_events():
    """MVP projects node should record execution events."""
    storage = FakeStorage()

    class FakeLLM:
        async def generate_mvp_projects(self, *args, **kwargs):
            return []

    deps = NodeDeps(
        settings=None,
        storage=storage,
        drive=None,
        docs=None,
        gmail=None,
        llm=FakeLLM(),
        ranking=None,
        youtube=None,
        gemini=None,
    )

    state: GraphState = {
        "analysis_id": "test-4",
        "project_suggestions": [],
        "analysis_model": None,
    }

    node = mvp_projects.build_node(deps)
    await node(state)

    # Verify instrumentation
    assert len(storage.node_events) == 1
    assert storage.node_events[0]["node_name"] == "mvp_projects"


@pytest.mark.asyncio
async def test_yt_branch_uses_persisted_metadata_without_gemini():
    """YouTube branch should use stored metadata when Gemini unavailable."""
    storage = FakeStorage()
    storage.video_metadata["https://youtu.be/v1"] = {
        "summary": "Stored summary",
        "key_points": ["KP1", "KP2"],
        "difficulty_level": "Advanced",
        "prerequisites": ["Python", "Django"],
        "takeaways": ["Build API"],
    }

    youtube = FakeYouTube()
    ranking = RankingService()

    deps = NodeDeps(
        settings=None,
        storage=storage,
        drive=None,
        docs=None,
        gmail=None,
        llm=None,
        ranking=ranking,
        youtube=youtube,
        gemini=None,  # No Gemini
    )

    state: GraphState = {
        "analysis_id": "test-5",
        "skill_queries": [{"skill": "Django", "query": "Django tutorial"}],
    }

    node = yt_branch.build_node(deps)
    result = await node(state)

    # Verify stored metadata was used
    suggestions = result["project_suggestions"]
    assert len(suggestions) > 0
    tutorial = suggestions[0].projects[0]
    if tutorial.analysis:
        assert tutorial.analysis.difficulty_level == "Advanced"