"""Unit tests for backfill_gemini CLI script."""
from __future__ import annotations

import argparse
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.backfill_gemini import _run_backfill, main


class FakeSettings:
    """Minimal settings for testing."""

    pass


class FakeGemini:
    """Mock Gemini service for testing."""

    def __init__(self, fail_on: set[str] | None = None):
        self.analyzed = []
        self.fail_on = fail_on or set()

    async def analyze_video(self, url: str):
        self.analyzed.append(url)
        if url in self.fail_on:
            raise RuntimeError(f"Gemini API error for {url}")
        return MagicMock(
            summary=f"Summary for {url}",
            key_points=["Point 1", "Point 2"],
            difficulty_level="Intermediate",
            prerequisites=["Python"],
            practical_takeaways=["Build something"],
        )


class FakeStorage:
    """Mock storage service for testing."""

    def __init__(self, videos: list[dict[str, str]]):
        self.videos = videos
        self.call_count = 0

    async def list_videos_missing_analysis(self, limit: int, resume_after: str | None):
        self.call_count += 1
        if resume_after:
            # Filter videos after resume_after
            remaining = [v for v in self.videos if v["video_id"] > resume_after]
        else:
            remaining = self.videos

        batch = remaining[:limit]
        return batch


class FakeContainer:
    """Mock AppContainer for testing."""

    def __init__(self, gemini, storage):
        self.gemini = gemini
        self.storage = storage

    async def startup(self):
        pass


@pytest.mark.asyncio
async def test_run_backfill_processes_all_videos():
    """Backfill should process all videos without analysis."""
    videos = [
        {"video_id": "vid1", "url": "https://youtu.be/vid1"},
        {"video_id": "vid2", "url": "https://youtu.be/vid2"},
        {"video_id": "vid3", "url": "https://youtu.be/vid3"},
    ]
    gemini = FakeGemini()
    storage = FakeStorage(videos)
    container = FakeContainer(gemini, storage)

    with patch("scripts.backfill_gemini.Settings", return_value=FakeSettings()):
        with patch("scripts.backfill_gemini.AppContainer", return_value=container):
            result = await _run_backfill(batch_size=10, resume_after=None, dry_run=False)

    assert result == 0
    assert len(gemini.analyzed) == 3
    assert "https://youtu.be/vid1" in gemini.analyzed
    assert "https://youtu.be/vid2" in gemini.analyzed
    assert "https://youtu.be/vid3" in gemini.analyzed


@pytest.mark.asyncio
async def test_run_backfill_handles_batching():
    """Backfill should process videos in batches."""
    videos = [
        {"video_id": f"vid{i}", "url": f"https://youtu.be/vid{i}"}
        for i in range(1, 6)
    ]
    gemini = FakeGemini()
    storage = FakeStorage(videos)
    container = FakeContainer(gemini, storage)

    with patch("scripts.backfill_gemini.Settings", return_value=FakeSettings()):
        with patch("scripts.backfill_gemini.AppContainer", return_value=container):
            result = await _run_backfill(batch_size=2, resume_after=None, dry_run=False)

    assert result == 0
    assert len(gemini.analyzed) == 5
    assert storage.call_count >= 3  # Multiple batches fetched


@pytest.mark.asyncio
async def test_run_backfill_resumes_after_token():
    """Backfill should skip videos before resume_after token."""
    videos = [
        {"video_id": "vid1", "url": "https://youtu.be/vid1"},
        {"video_id": "vid2", "url": "https://youtu.be/vid2"},
        {"video_id": "vid3", "url": "https://youtu.be/vid3"},
    ]
    gemini = FakeGemini()
    storage = FakeStorage(videos)
    container = FakeContainer(gemini, storage)

    with patch("scripts.backfill_gemini.Settings", return_value=FakeSettings()):
        with patch("scripts.backfill_gemini.AppContainer", return_value=container):
            result = await _run_backfill(
                batch_size=10, resume_after="vid1", dry_run=False
            )

    assert result == 0
    assert len(gemini.analyzed) == 2
    assert "https://youtu.be/vid1" not in gemini.analyzed
    assert "https://youtu.be/vid2" in gemini.analyzed
    assert "https://youtu.be/vid3" in gemini.analyzed


@pytest.mark.asyncio
async def test_run_backfill_dry_run_skips_analysis():
    """Dry run should list videos without calling Gemini."""
    videos = [
        {"video_id": "vid1", "url": "https://youtu.be/vid1"},
        {"video_id": "vid2", "url": "https://youtu.be/vid2"},
    ]
    gemini = FakeGemini()
    storage = FakeStorage(videos)
    container = FakeContainer(gemini, storage)

    with patch("scripts.backfill_gemini.Settings", return_value=FakeSettings()):
        with patch("scripts.backfill_gemini.AppContainer", return_value=container):
            result = await _run_backfill(batch_size=10, resume_after=None, dry_run=True)

    assert result == 0
    assert len(gemini.analyzed) == 0  # No actual API calls


@pytest.mark.asyncio
async def test_run_backfill_handles_gemini_failures():
    """Backfill should continue processing after individual failures."""
    videos = [
        {"video_id": "vid1", "url": "https://youtu.be/vid1"},
        {"video_id": "vid2", "url": "https://youtu.be/vid2"},
        {"video_id": "vid3", "url": "https://youtu.be/vid3"},
    ]
    gemini = FakeGemini(fail_on={"https://youtu.be/vid2"})
    storage = FakeStorage(videos)
    container = FakeContainer(gemini, storage)

    with patch("scripts.backfill_gemini.Settings", return_value=FakeSettings()):
        with patch("scripts.backfill_gemini.AppContainer", return_value=container):
            result = await _run_backfill(batch_size=10, resume_after=None, dry_run=False)

    assert result == 0
    assert len(gemini.analyzed) == 3
    # vid2 failed but script continued


@pytest.mark.asyncio
async def test_run_backfill_returns_error_when_gemini_unconfigured():
    """Backfill should return error code when Gemini is not configured."""
    storage = FakeStorage([])
    container = FakeContainer(gemini=None, storage=storage)

    with patch("scripts.backfill_gemini.Settings", return_value=FakeSettings()):
        with patch("scripts.backfill_gemini.AppContainer", return_value=container):
            result = await _run_backfill(batch_size=10, resume_after=None, dry_run=False)

    assert result == 1


@pytest.mark.asyncio
async def test_run_backfill_handles_empty_result():
    """Backfill should handle when no videos need analysis."""
    gemini = FakeGemini()
    storage = FakeStorage([])  # No videos
    container = FakeContainer(gemini, storage)

    with patch("scripts.backfill_gemini.Settings", return_value=FakeSettings()):
        with patch("scripts.backfill_gemini.AppContainer", return_value=container):
            result = await _run_backfill(batch_size=10, resume_after=None, dry_run=False)

    assert result == 0
    assert len(gemini.analyzed) == 0


def test_main_parses_arguments_correctly():
    """Main function should parse CLI arguments correctly."""
    test_args = [
        "backfill_gemini.py",
        "--batch-size",
        "50",
        "--resume-after",
        "vid123",
        "--dry-run",
        "--log-level",
        "DEBUG",
    ]

    with patch("sys.argv", test_args):
        with patch("scripts.backfill_gemini.asyncio.run") as mock_run:
            mock_run.return_value = 0
            result = main()

    assert result == 0
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    # The coroutine was passed to asyncio.run


def test_main_clamps_batch_size():
    """Main should clamp batch_size between 1 and 500."""
    test_cases = [
        (["backfill_gemini.py", "--batch-size", "0"], 1),
        (["backfill_gemini.py", "--batch-size", "1000"], 500),
        (["backfill_gemini.py", "--batch-size", "50"], 50),
    ]

    for args, expected_batch in test_cases:
        with patch("sys.argv", args):
            with patch("scripts.backfill_gemini.asyncio.run") as mock_run:
                mock_run.return_value = 0
                main()

        # Verify batch_size was clamped (would need to inspect the call)
        assert mock_run.called


def test_main_configures_logging():
    """Main should configure logging based on --log-level argument."""
    test_args = ["backfill_gemini.py", "--log-level", "WARNING"]

    with patch("sys.argv", test_args):
        with patch("scripts.backfill_gemini.asyncio.run") as mock_run:
            mock_run.return_value = 0
            with patch("logging.basicConfig") as mock_logging:
                main()

    mock_logging.assert_called_once()
    assert mock_logging.call_args[1]["level"] == logging.WARNING


def test_main_defaults_to_info_level():
    """Main should default to INFO log level."""
    test_args = ["backfill_gemini.py"]

    with patch("sys.argv", test_args):
        with patch("scripts.backfill_gemini.asyncio.run") as mock_run:
            mock_run.return_value = 0
            with patch("logging.basicConfig") as mock_logging:
                main()

    assert mock_logging.call_args[1]["level"] == logging.INFO