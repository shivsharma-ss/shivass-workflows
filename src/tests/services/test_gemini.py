"""Tests for GeminiService Google GenAI integration."""

import json
from types import SimpleNamespace

import pytest

from services.gemini import GeminiService


class FakeStorage:
    def __init__(self, metadata=None):
        self.metadata = metadata or {}
        self.saved = []

    async def get_youtube_video_metadata(self, url):
        return self.metadata.get(url)

    async def save_youtube_video_metadata(self, video_url, **payload):
        self.saved.append((video_url, payload))
        self.metadata[video_url] = payload


class FakeModels:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=json.dumps(self.payload))


class FakeClient:
    def __init__(self, models):
        self.models = models


@pytest.mark.asyncio
async def test_gemini_service_uses_models_api_and_parses_text():
    """GeminiService should call client.models.generate_content and parse JSON text."""
    payload = {
        "summary": "Video overview",
        "key_points": ["Point"],
        "difficulty_level": "Beginner",
        "prerequisites": ["Python"],
        "practical_takeaways": ["Build a demo"],
    }
    models = FakeModels(payload)
    client = FakeClient(models)
    service = GeminiService(api_key="test", cache=None, client=client)

    result = await service.analyze_video("https://youtu.be/demo")

    assert result is not None
    assert result.summary == "Video overview"
    assert models.calls and models.calls[0]["model"] == service._model


@pytest.mark.asyncio
async def test_gemini_service_reuses_persisted_metadata():
    """When structured metadata exists in storage, Gemini should skip API calls."""
    models = FakeModels(payload={"unused": True})
    client = FakeClient(models)
    storage = FakeStorage(
        metadata={
            "https://youtu.be/demo": {
                "summary": "Stored",
                "key_points": ["KP"],
                "difficulty_level": "Intermediate",
                "prerequisites": ["Python"],
                "takeaways": ["Ship"],
            }
        }
    )
    service = GeminiService(api_key="test", cache=None, storage=storage, client=client)

    result = await service.analyze_video("https://youtu.be/demo")

    assert result is not None
    assert result.summary == "Stored"
    assert models.calls == []  # storage hit avoided API usage


@pytest.mark.asyncio
async def test_gemini_service_persists_results():
    """Gemini responses should be persisted for future runs."""
    payload = {
        "summary": "Fresh",
        "key_points": ["KP"],
        "difficulty_level": "Beginner",
        "prerequisites": ["Python"],
        "practical_takeaways": ["Ship"],
    }
    models = FakeModels(payload)
    client = FakeClient(models)
    storage = FakeStorage()
    service = GeminiService(api_key="test", cache=None, storage=storage, client=client)

    await service.analyze_video("https://youtu.be/demo")

    assert storage.saved
    saved_payload = storage.saved[0][1]
    assert saved_payload["summary"] == "Fresh"
    assert saved_payload["key_points"] == ["KP"]
