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

    await storage.update_status("a1", AnalysisStatus.RUNNING, {"step": "ingest"})
    updated = await storage.get_analysis("a1")
    assert updated is not None
    assert updated.status == AnalysisStatus.RUNNING
    assert updated.payload["step"] == "ingest"

    await storage.set_approval_token("a1", "token123")
    again = await storage.get_analysis("a1")
    assert again.approval_token == "token123"

    await storage.save_artifact("a1", "cv_text", "sample cv")
    artifact = await storage.get_artifact("a1", "cv_text")
    assert artifact == "sample cv"

    suggestion = TutorialSuggestion(
        tutorialTitle="Sample",
        tutorialUrl="https://example.com/tutorial",
        personalizationTip="Do it",
    )
    await storage.save_artifact("a1", "suggestion", suggestion)
    suggestion_artifact = await storage.get_artifact("a1", "suggestion")
    assert "https://example.com/tutorial" in suggestion_artifact

    await storage.save_youtube_cache("python tutorial", [{"video_id": "1"}])
    cache_hit = await storage.get_youtube_cache("python tutorial", max_age_seconds=3600)
    assert cache_hit == [{"video_id": "1"}]

    cache_miss = await storage.get_youtube_cache("python tutorial", max_age_seconds=-1)
    assert cache_miss is None

    await storage.save_youtube_video_metadata("https://youtu.be/vid", "desc", ["python"], ["tensorflow"])
    metadata = await storage.get_youtube_video_metadata("https://youtu.be/vid")
    assert metadata["skills"] == ["python"]


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
    assert [run.analysis_id for run in all_runs] == ["a2", "a1"]

    completed_runs = await storage.list_analyses(status=AnalysisStatus.COMPLETED)
    assert len(completed_runs) == 1
    assert completed_runs[0].analysis_id == "a2"

    artifacts = await storage.list_artifacts("a2")
    assert [item["artifact_type"] for item in artifacts] == ["details", "summary"]
    assert "second artifact" in artifacts[-1]["content"]
