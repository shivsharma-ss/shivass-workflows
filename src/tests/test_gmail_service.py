"""Unit tests for the GmailService OAuth credential handling."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytest

from services.gmail import GmailService


class InMemoryTokenStore:
    """Simple async-compatible token store for tests."""

    def __init__(self, initial: Optional[dict[str, Any]] = None):
        self.value = initial
        self.saved: Optional[dict[str, Any]] = None

    async def get(self, provider: str, account: str) -> Optional[dict[str, Any]]:
        return self.value

    async def save(self, provider: str, account: str, credentials: dict[str, Any]) -> None:
        self.saved = credentials
        self.value = credentials


@pytest.mark.asyncio
async def test_gmail_service_sends_with_oauth_tokens(monkeypatch, tmp_path):
    """GmailService should use stored OAuth tokens to send mail."""

    expiry = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    token_store = InMemoryTokenStore(
        {
            "token": "ya29.test",
            "refresh_token": "1//refresh",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client",
            "client_secret": "secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.send"],
            "expiry": expiry,
        }
    )
    sent_messages: list[dict[str, Any]] = []

    class FakeMessages:
        def send(self, userId: str, body: dict[str, Any]) -> Any:
            sent_messages.append(body)

            class Exec:
                def execute(self_inner):
                    return {"id": "1"}

            return Exec()

    class FakeUsers:
        def messages(self) -> FakeMessages:
            return FakeMessages()

    class FakeGmail:
        def users(self) -> FakeUsers:
            return FakeUsers()

    def fake_build(api: str, version: str, credentials=None):
        assert api == "gmail"
        return FakeGmail()

    monkeypatch.setattr("services.gmail.build", fake_build)

    service = GmailService(
        templates_path=str(tmp_path),
        sender="sender@example.com",
        subject_override=None,
        oauth_token_store=token_store,
        smtp_server=None,
        smtp_port=587,
        smtp_username=None,
        smtp_password=None,
    )
    result = await service.send_html("user@example.com", "Subject", "<p>Body</p>")
    assert result["id"] == "1"
    assert sent_messages


@pytest.mark.asyncio
async def test_gmail_service_requires_credentials(tmp_path):
    """If no OAuth tokens or service-account credentials exist, raise helpful error."""

    token_store = InMemoryTokenStore()
    service = GmailService(
        templates_path=str(tmp_path),
        sender="sender@example.com",
        subject_override=None,
        oauth_token_store=token_store,
        smtp_server=None,
        smtp_port=587,
        smtp_username=None,
        smtp_password=None,
    )
    with pytest.raises(RuntimeError):
        await service.send_html("user@example.com", "Subject", "<p>Body</p>")


@pytest.mark.asyncio
async def test_gmail_service_falls_back_to_smtp(monkeypatch, tmp_path):
    """If Gmail credentials are missing, SMTP fallback should send."""

    token_store = InMemoryTokenStore()
    sent_messages = []

    class DummySMTP:
        def __init__(self, host, port, timeout=30):
            self.host = host
            self.port = port
            self.timeout = timeout

        def starttls(self):
            return None

        def login(self, username, password):
            sent_messages.append(("login", username, password))

        def sendmail(self, sender, recipients, content):
            sent_messages.append(("send", sender, recipients, content))

        def quit(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("services.gmail.smtplib.SMTP", DummySMTP)

    service = GmailService(
        templates_path=str(tmp_path),
        sender="sender@example.com",
        subject_override=None,
        oauth_token_store=token_store,
        smtp_server="smtp.example.com",
        smtp_port=587,
        smtp_username="smtp-user",
        smtp_password="smtp-pass",
    )
    result = await service.send_html("user@example.com", "Subject", "<p>Body</p>")
    assert sent_messages
    assert result["transport"] == "smtp"
