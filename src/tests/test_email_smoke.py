"""Optional smoke test that sends a real Hello World email when enabled."""
from __future__ import annotations

import os

import pytest

from app.config import get_settings
from services.container import AppContainer


EMAIL_SMOKE_ENABLED = bool(os.environ.get("EMAIL_SMOKE_RECIPIENT"))


@pytest.mark.asyncio
@pytest.mark.skipif(
    not EMAIL_SMOKE_ENABLED,
    reason="Set EMAIL_SMOKE_RECIPIENT in .env to run the real email smoke test",
)
async def test_send_hello_world_email():
    """Sends a Hello World email using the configured Gmail service."""

    settings = get_settings()
    container = AppContainer(settings)
    await container.storage.initialize()
    html = "<p>Hello World!</p>"
    result = await container.gmail.send_html(settings.email_smoke_recipient, "Hello World!", html)
    assert result
