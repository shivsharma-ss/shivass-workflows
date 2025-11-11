"""Tests for GeminiService Google GenAI integration."""

import json
from types import SimpleNamespace

import pytest

from services.gemini import GeminiService


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
