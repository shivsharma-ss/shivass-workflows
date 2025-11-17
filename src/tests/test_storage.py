"""StorageService persistence lifecycle tests."""

import pytest

from app.schemas import AnalysisStatus, TutorialSuggestion
from services.storage import StorageService


@pytest.mark.asyncio
async def test_storage_lifecycle(tmp_path):
    """Verify create/update/token operations persist correctly in sqlite."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'storage.db'}"
    storage = StorageService(db_url)
    await storage.initialize()

    await storage.create_analysis("a1", "user@example.com", "doc", {"foo": "bar"})
    record = await storage.get_analysis("a1")
    assert record is not None
    assert record.status == AnalysisStatus.PENDING
    history = await storage.get_status_history("a1")
    assert len(history) == 1

    await storage.update_status("a1", AnalysisStatus.RUNNING, {"step": "ingest"})
    updated = await storage.get_analysis("a1")
    assert updated is not None
    assert updated.status == AnalysisStatus.RUNNING
    assert updated.payload["step"] == "ingest"
    history = await storage.get_status_history("a1")
    assert [entry["status"] for entry in history] == [AnalysisStatus.PENDING.value, AnalysisStatus.RUNNING.value]

    await storage.set_approval_token("a1", "token123")
    again = await storage.get_analysis("a1")
    assert again.approval_token == "token123"

    await storage.save_artifact("a1", "cv_text", "sample cv")
    await storage.save_artifact("a1", "cv_text", "updated cv")
    artifact = await storage.get_artifact("a1", "cv_text")
    assert artifact == "updated cv"
    artifact_versions = await storage.list_artifacts("a1")
    assert artifact_versions[0]["version"] == 2
    assert artifact_versions[-1]["version"] == 1

    suggestion = TutorialSuggestion(
        tutorialTitle="Sample",
        tutorialUrl="https://example.com/tutorial",
        personalizationTip="Do it",
    )
    await storage.save_artifact("a1", "suggestion", suggestion)
    suggestion_artifact = await storage.get_artifact("a1", "suggestion")
    assert "https://example.com/tutorial" in suggestion_artifact

    await storage.save_youtube_cache("python tutorial", [{"video_id": "1", "url": "https://youtu.be/1"}])
    cache_hit = await storage.get_youtube_cache("python tutorial", max_age_seconds=3600)
    assert cache_hit == [{"video_id": "1", "url": "https://youtu.be/1"}]

    cache_miss = await storage.get_youtube_cache("python tutorial", max_age_seconds=-1)
    assert cache_miss is None

    await storage.save_youtube_video_metadata(
        "https://youtu.be/vid",
        summary="desc",
        skills=["python"],
        tech_stack=["tensorflow"],
        key_points=["KP"],
        difficulty_level="Intermediate",
        prerequisites=["Python"],
        takeaways=["Ship"],
    )
    metadata = await storage.get_youtube_video_metadata("https://youtu.be/vid")
    assert metadata["skills"] == ["python"]
    assert metadata["key_points"] == ["KP"]
    assert metadata["difficulty_level"] == "Intermediate"

    await storage.save_oauth_credentials("google", "user@example.com", {"token": "v1"})
    await storage.save_oauth_credentials("google", "user@example.com", {"token": "v2"})
    creds = await storage.get_oauth_credentials("google", "user@example.com")
    assert creds == {"token": "v2"}

    await storage.record_node_event(
        "a1",
        "test_node",
        state_before={"step": "before"},
        output={"step": "after"},
    )
    events = await storage.list_node_events("a1")
    assert events[-1]["node_name"] == "test_node"


@pytest.mark.asyncio
async def test_list_analyses_and_artifacts(tmp_path):
    """Verify list endpoints surface most recent analyses and artifacts."""

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'storage.db'}"
    storage = StorageService(db_url)
    await storage.initialize()

    await storage.create_analysis("a1", "user1@example.com", "doc1", {"foo": "bar"})
    await storage.update_status("a1", AnalysisStatus.RUNNING)
    await storage.save_artifact("a1", "summary", "first artifact")

    await storage.create_analysis("a2", "user2@example.com", "doc2", {"foo": "baz"})
    await storage.update_status("a2", AnalysisStatus.COMPLETED)
    await storage.save_artifact("a2", "summary", "second artifact")
    await storage.save_artifact("a2", "details", {"score": 95})

    all_runs = await storage.list_analyses()
    assert {run.analysis_id for run in all_runs} == {"a2", "a1"}

    completed_runs = await storage.list_analyses(status=AnalysisStatus.COMPLETED)
    assert len(completed_runs) == 1
    assert completed_runs[0].analysis_id == "a2"

    artifacts = await storage.list_artifacts("a2")
    assert {item["artifact_type"] for item in artifacts} == {"details", "summary"}
    assert any("second artifact" in artifact["content"] for artifact in artifacts)


@pytest.mark.asyncio
async def test_list_videos_missing_analysis(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'storage.db'}"
    storage = StorageService(db_url)
    await storage.initialize()

    await storage.save_youtube_video_metadata("https://youtu.be/vid-missing", summary="desc only")
    await storage.save_youtube_video_metadata("https://youtu.be/vid-later", summary="desc only")
    pending = await storage.list_videos_missing_analysis(limit=10)
    ids = [row["video_id"] for row in pending]
    assert ids == ["vid-later", "vid-missing"]

    await storage.save_youtube_video_metadata(
        "https://youtu.be/vid-missing",
        summary="desc",
        key_points=["KP"],
        difficulty_level="Intermediate",
        prerequisites=["Python"],
        takeaways=["Ship"],
    )
    remaining = await storage.list_videos_missing_analysis(limit=10)
    assert any(row["video_id"] == "vid-later" for row in remaining)
    assert all(row["video_id"] != "vid-missing" for row in remaining)
    resume_filtered = await storage.list_videos_missing_analysis(limit=10, resume_after="vid-missing")
    assert all(row["video_id"] > "vid-missing" for row in resume_filtered)


@pytest.mark.asyncio
async def test_update_status_without_payload_preserves_existing_data(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'storage.db'}"
    storage = StorageService(db_url)
    await storage.initialize()
    await storage.create_analysis("a1", "user@example.com", "doc", {"foo": "bar"})
    await storage.update_status("a1", AnalysisStatus.COMPLETED)
    record = await storage.get_analysis("a1")
    assert record is not None
    assert record.payload["foo"] == "bar"
    assert record.status == AnalysisStatus.COMPLETED


def test_storage_requires_sqlite_backend():
    with pytest.raises(ValueError):
        StorageService("postgresql://user:pass@localhost/db")


@pytest.mark.asyncio
async def test_initialize_idempotent(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'storage.db'}"
    storage = StorageService(db_url)
    await storage.initialize()
    await storage.initialize()
    await storage.create_analysis("check", "user@example.com", "doc", {})
    record = await storage.get_analysis("check")
    assert record is not None


@pytest.mark.asyncio
async def test_runner_kickoff_background_mode(tmp_path):
    """Runner should start analysis in background when background=True."""
    from orchestrator.runner import OrchestratorRunner
    from app.schemas import AnalysisRequest

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'runner.db'}"
    storage = StorageService(db_url)
    await storage.initialize()

    # Create minimal deps and graph
    deps = NodeDeps(
        settings=None,
        storage=storage,
        drive=None,
        docs=None,
        gmail=None,
        llm=None,
        ranking=None,
        youtube=None,
        gemini=None,
    )

    async def mock_graph_invoke(state):
        await asyncio.sleep(0.1)  # Simulate work
        return state

    from unittest.mock import AsyncMock
    mock_graph = AsyncMock()
    mock_graph.ainvoke = mock_graph_invoke

    runner = OrchestratorRunner(mock_graph, deps)

    request = AnalysisRequest(
        email="test@example.com",
        cvDocId="doc123",
        jobDescription="Job desc",
    )

    analysis_id, status = await runner.kickoff(request, background=True)

    assert status == AnalysisStatus.PENDING
    assert analysis_id is not None

    # Give background task time to start
    await asyncio.sleep(0.05)

    # Analysis should exist
    record = await storage.get_analysis(analysis_id)
    assert record is not None


@pytest.mark.asyncio
async def test_storage_record_node_event(tmp_path):
    """Storage should persist node execution events."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'storage.db'}"
    storage = StorageService(db_url)
    await storage.initialize()

    await storage.create_analysis("a1", "user@example.com", "doc", {})

    await storage.record_node_event(
        analysis_id="a1",
        node_name="test_node",
        state_before={"input": "data"},
        output={"result": "success"},
        started_at="2024-01-01T00:00:00Z",
        error=None,
    )

    # Verify event was stored (requires additional query method)
    async with storage._connection(row_factory=True) as db:
        async with db.execute(
            "SELECT * FROM node_events WHERE analysis_id = ? AND node_name = ?",
            ("a1", "test_node"),
        ) as cursor:
            row = await cursor.fetchone()

    assert row is not None
    assert row["node_name"] == "test_node"
    assert row["error"] is None


@pytest.mark.asyncio
async def test_storage_list_videos_missing_analysis(tmp_path):
    """Storage should list videos without Gemini analysis."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'storage.db'}"
    storage = StorageService(db_url)
    await storage.initialize()

    # Insert videos with and without analysis
    async with storage._connection() as db:
        await db.execute(
            "INSERT INTO youtube_videos (video_id, title, url) VALUES (?, ?, ?)",
            ("vid1", "Video 1", "https://youtu.be/vid1"),
        )
        await db.execute(
            "INSERT INTO youtube_videos (video_id, title, url) VALUES (?, ?, ?)",
            ("vid2", "Video 2", "https://youtu.be/vid2"),
        )
        await db.execute(
            "INSERT INTO youtube_videos (video_id, title, url) VALUES (?, ?, ?)",
            ("vid3", "Video 3", "https://youtu.be/vid3"),
        )
        # Add analysis for vid2
        await db.execute(
            "INSERT INTO video_analyses (video_id, model, summary) VALUES (?, ?, ?)",
            ("vid2", "gemini-2.5-flash", "Summary"),
        )
        await db.commit()

    missing = await storage.list_videos_missing_analysis(limit=10, resume_after=None)

    assert len(missing) == 2
    video_ids = {row["video_id"] for row in missing}
    assert "vid1" in video_ids
    assert "vid3" in video_ids
    assert "vid2" not in video_ids


@pytest.mark.asyncio
async def test_storage_get_status_history(tmp_path):
    """Storage should return chronological status history."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'storage.db'}"
    storage = StorageService(db_url)
    await storage.initialize()

    await storage.create_analysis("a1", "user@example.com", "doc", {})
    await storage.update_status("a1", AnalysisStatus.RUNNING, {"step": "ingest"})
    await storage.update_status("a1", AnalysisStatus.COMPLETED, {"step": "done"})

    history = await storage.get_status_history("a1")

    assert len(history) == 3  # pending, running, completed
    assert history[0]["status"] == AnalysisStatus.PENDING.value
    assert history[1]["status"] == AnalysisStatus.RUNNING.value
    assert history[2]["status"] == AnalysisStatus.COMPLETED.value
