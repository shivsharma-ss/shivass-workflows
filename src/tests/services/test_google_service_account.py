from __future__ import annotations

import pytest
from google.auth.exceptions import RefreshError

from services.google_service_account import ServiceAccountCredentialChain


class DummyCredentials:
    def __init__(self, name: str = "base") -> None:
        self.name = name
        self.service_account_email = "svc@example.com"
        self.last_subject: str | None = None

    def with_subject(self, subject: str) -> "DummyCredentials":
        self.last_subject = subject
        delegated = DummyCredentials(name="delegated")
        delegated.impersonated_subject = subject
        return delegated


def _install_stub(monkeypatch) -> DummyCredentials:
    base = DummyCredentials()
    monkeypatch.setattr(
        "services.google_service_account.Credentials.from_service_account_file",
        lambda *_, **__: base,
    )
    return base


def test_run_uses_base_credentials_without_subject(monkeypatch):
    base = _install_stub(monkeypatch)
    chain = ServiceAccountCredentialChain("svc.json", ["scope"], subject=None)

    result = chain.run(lambda creds: creds.name)

    assert result == "base"
    assert base.last_subject is None


def test_run_prefers_delegated_credentials_when_available(monkeypatch):
    _install_stub(monkeypatch)
    chain = ServiceAccountCredentialChain("svc.json", ["scope"], subject="user@example.com")
    seen: list[str] = []

    chain.run(lambda creds: seen.append(creds.name) or "ok")

    assert seen == ["delegated"]


def test_run_falls_back_to_service_account_on_refresh_error(monkeypatch, caplog):
    _install_stub(monkeypatch)
    chain = ServiceAccountCredentialChain("svc.json", ["scope"], subject="user@example.com")
    calls: list[str] = []

    def _call(creds):
        calls.append(creds.name)
        if creds.name == "delegated":
            raise RefreshError("unauthorized_client")
        return "ok"

    with caplog.at_level("WARNING"):
        result = chain.run(_call)

    assert result == "ok"
    assert calls == ["delegated", "base"]
    assert "retrying without domain delegation" in caplog.text


def test_blank_subject_is_treated_as_none(monkeypatch):
    base = _install_stub(monkeypatch)
    chain = ServiceAccountCredentialChain("svc.json", ["scope"], subject="")

    assert chain.run(lambda creds: creds.name) == "base"
    assert base.last_subject is None


def test_refresh_error_from_base_is_raised(monkeypatch):
    _install_stub(monkeypatch)
    chain = ServiceAccountCredentialChain("svc.json", ["scope"], subject=None)

    def _call(_):
        raise RefreshError("boom")

    with pytest.raises(RefreshError):
        chain.run(_call)
