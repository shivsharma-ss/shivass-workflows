"""Optional smoke test that sends a real Hello World email when enabled."""
from __future__ import annotations

import os

import pytest

from app.config import get_settings
from services.container import AppContainer


@pytest.mark.asyncio
@pytest.mark.skipif(
    not get_settings().email_smoke_recipient,
    reason="Set EMAIL_SMOKE_RECIPIENT in .env to run the real email smoke test",
)
async def test_send_hello_world_email():
    """Sends a Hello World email using the configured Gmail service."""

    settings = get_settings()
    if not settings.email_smoke_recipient:
        pytest.skip("EMAIL_SMOKE_RECIPIENT not set in settings")
    container = AppContainer(settings)
    await container.storage.initialize()
    html = "<p>Hello World!</p>"
    result = await container.gmail.send_html(settings.email_smoke_recipient, "Hello World!", html)
    assert result
