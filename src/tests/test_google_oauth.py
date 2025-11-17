"""Tests for GoogleOAuthService helper flows."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from services.google_oauth import GoogleOAuthService


class DummyFlow:
    """Tiny Flow replacement so tests can run without google-auth libs."""

    def __init__(self, state: str | None = None) -> None:
        self.state = state
        self.redirect_uri = None
        self.authorization_calls: list[dict[str, str]] = []
        self.oauth2session = SimpleNamespace(scope_change_wizardry=False, token=None)

    def authorization_url(self, **kwargs):
        self.authorization_calls.append(kwargs)
        return ("https://auth.test/consent", self.state or "state-123")


class DummyResponse:
    def __init__(self, status_code: int, payload: dict[str, str]):
        self._status = status_code
        self._payload = payload

    def raise_for_status(self):
        if self._status >= 400:
            raise httpx.HTTPStatusError(
                "boom",
                request=httpx.Request("GET", "https://example.com"),
                response=httpx.Response(self._status),
            )

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def immediate_to_thread(monkeypatch):
    async def _immediate(func, *args, **kwargs):  # type: ignore[override]
        return func(*args, **kwargs)

    monkeypatch.setattr("services.google_oauth.asyncio", SimpleNamespace(to_thread=_immediate))


@pytest.fixture
def service(monkeypatch):
    svc = GoogleOAuthService(
        client_id="client",
        client_secret="secret",
        redirect_uri="https://app/callback",
        token_uri="https://oauth2/token",
        scopes=["openid", "email"],
    )

    def fake_build(self, state=None):  # type: ignore[override]
        return DummyFlow(state=state)

    monkeypatch.setattr(GoogleOAuthService, "_build_flow", fake_build)
    return svc


def test_generate_authorize_url_uses_flow_and_returns_state(service):
    url, state = service.generate_authorize_url()
    assert url == "https://auth.test/consent"
    assert state == "state-123"


@pytest.mark.asyncio
async def test_exchange_code_returns_email_from_id_token(service, monkeypatch):
    def fake_fetch(self, flow, code):  # type: ignore[override]
        assert flow.redirect_uri == "https://app/callback"
        return SimpleNamespace(
            token="ya29",
            refresh_token="refresh",
            token_uri=service._token_uri,
            client_id=service._client_id,
            client_secret=service._client_secret,
            scopes=service._scopes,
            expiry=datetime.now(timezone.utc),
            id_token="signed-token",
        )

    monkeypatch.setattr(GoogleOAuthService, "_fetch_token", fake_fetch)
    monkeypatch.setattr(
        "services.google_oauth.id_token.verify_oauth2_token",
        lambda token, request, audience: {"email": "owner@example.com"},
    )

    payload, email = await service.exchange_code("code-123", state="state-123")
    assert payload["token"] == "ya29"
    assert payload["refresh_token"] == "refresh"
    assert email == "owner@example.com"


@pytest.mark.asyncio
async def test_exchange_code_fetches_userinfo_when_id_token_missing(service, monkeypatch):
    def fake_fetch(self, flow, code):  # type: ignore[override]
        return SimpleNamespace(
            token="access-token",
            refresh_token="refresh",
            token_uri=service._token_uri,
            client_id=service._client_id,
            client_secret=service._client_secret,
            scopes=service._scopes,
            expiry=None,
            id_token=None,
        )

    class DummyClient:
        def __init__(self, response):
            self._response = response

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, headers=None):
            assert headers["Authorization"].startswith("Bearer access-token")
            return self._response

    monkeypatch.setattr(GoogleOAuthService, "_fetch_token", fake_fetch)
    monkeypatch.setattr(
        "services.google_oauth.id_token.verify_oauth2_token",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        "services.google_oauth.httpx.AsyncClient",
        lambda timeout=10: DummyClient(DummyResponse(200, {"email": "profile@example.com"})),
    )

    payload, email = await service.exchange_code("code", state="state-123")
    assert email == "profile@example.com"
    assert payload["token"] == "access-token"


@pytest.mark.asyncio
async def test_exchange_code_raises_when_email_cannot_be_resolved(service, monkeypatch):
    def fake_fetch(self, flow, code):  # type: ignore[override]
        return SimpleNamespace(
            token="access-token",
            refresh_token="refresh",
            token_uri=service._token_uri,
            client_id=service._client_id,
            client_secret=service._client_secret,
            scopes=service._scopes,
            expiry=None,
            id_token=None,
        )

    monkeypatch.setattr(GoogleOAuthService, "_fetch_token", fake_fetch)
    monkeypatch.setattr(
        "services.google_oauth.id_token.verify_oauth2_token",
        lambda *args, **kwargs: {},
    )
    class MissingEmailClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, headers=None):
            return DummyResponse(200, {})

    monkeypatch.setattr("services.google_oauth.httpx.AsyncClient", lambda timeout=10: MissingEmailClient())

    with pytest.raises(RuntimeError):
        await service.exchange_code("code", state="state-123")


@pytest.mark.asyncio
async def test_exchange_code_surfaces_userinfo_http_errors(service, monkeypatch):
    def fake_fetch(self, flow, code):  # type: ignore[override]
        return SimpleNamespace(
            token="access-token",
            refresh_token="refresh",
            token_uri=service._token_uri,
            client_id=service._client_id,
            client_secret=service._client_secret,
            scopes=service._scopes,
            expiry=None,
            id_token=None,
        )

    class ErroringClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, headers=None):
            return DummyResponse(403, {})

    monkeypatch.setattr(GoogleOAuthService, "_fetch_token", fake_fetch)
    monkeypatch.setattr(
        "services.google_oauth.id_token.verify_oauth2_token",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr("services.google_oauth.httpx.AsyncClient", lambda timeout=10: ErroringClient())

    with pytest.raises(httpx.HTTPStatusError):
        await service.exchange_code("code", state="state-123")
