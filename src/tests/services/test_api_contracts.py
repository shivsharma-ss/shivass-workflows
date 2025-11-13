"""Contract tests that exercise FastAPI routes with a fake container."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app import routes as routes_module
from app.routes import router
from app.schemas import (
    AnalysisArtifact,
    AnalysisListResponse,
    AnalysisRequest,
    AnalysisResponse,
    AnalysisStatus,
    AnalysisStatusResponse,
)
from services.storage import AnalysisRecord


class FakeStorage:
    def __init__(self):
        now = datetime(2024, 1, 1, tzinfo=timezone.utc)
        self.records: dict[str, AnalysisRecord] = {
            "seed": AnalysisRecord(
                analysis_id="seed",
                email="seed@example.com",
                cv_doc_id="doc-1",
                status=AnalysisStatus.RUNNING,
                payload={"stage": "ingest"},
                approval_token=None,
                last_error=None,
                created_at=now,
                updated_at=now,
            )
        }
        self.artifacts = {
            "seed": [
                {
                    "artifact_type": "summary",
                    "content": "{\"score\":90}",
                    "created_at": now.isoformat(),
                }
            ]
        }

    async def list_analyses(self, limit=50, status=None):
        items = list(self.records.values())
        if status:
            items = [item for item in items if item.status == status]
        return items[:limit]

    async def get_analysis(self, analysis_id: str):
        return self.records.get(analysis_id)

    async def list_artifacts(self, analysis_id: str):
        return self.artifacts.get(analysis_id, [])

    async def save_artifact(self, analysis_id: str, artifact_type: str, content: str):
        payload = {
            "artifact_type": artifact_type,
            "content": content,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.artifacts.setdefault(analysis_id, []).append(payload)


class FakeRunner:
    def __init__(self, storage: FakeStorage):
        self.storage = storage
        self.resume_calls: list[str] = []

    async def kickoff(self, payload: AnalysisRequest):
        analysis_id = f"run-{len(self.storage.records) + 1}"
        now = datetime.now(timezone.utc)
        record = AnalysisRecord(
            analysis_id=analysis_id,
            email=payload.email,
            cv_doc_id=payload.cvDocId,
            status=AnalysisStatus.PENDING,
            payload=payload.model_dump(),
            approval_token=None,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        self.storage.records[analysis_id] = record
        return analysis_id, record.status

    async def resume(self, analysis_id: str):
        self.resume_calls.append(analysis_id)
        record = self.storage.records[analysis_id]
        record.status = AnalysisStatus.COMPLETED
        return record.status


class FakeCache:
    def __init__(self):
        self.values: dict[str, dict[str, str]] = {}

    async def set(self, key, value, ttl_seconds=600):
        self.values[key] = value

    async def get(self, key):
        return self.values.get(key)


class FakeOAuth:
    def __init__(self):
        self.last_code: str | None = None

    def generate_authorize_url(self):
        return "https://accounts.test/auth", "state-token"

    async def exchange_code(self, code: str, state: str | None = None):
        self.last_code = code
        return {"token": "ya29"}, "sender@example.com"


class FakeTokenStore:
    def __init__(self):
        self.saved: list[tuple[str, str, dict[str, str]]] = []

    async def save(self, provider: str, account: str, credentials: dict[str, str]):
        self.saved.append((provider, account, credentials))


class FakeContainer:
    def __init__(self):
        self.storage = FakeStorage()
        self.runner = FakeRunner(self.storage)
        self.cache = FakeCache()
        self.google_oauth = FakeOAuth()
        self.token_store = FakeTokenStore()
        self.settings = SimpleNamespace(gmail_sender="sender@example.com")


@pytest.fixture
def api_client(monkeypatch):
    container = FakeContainer()
    app = FastAPI()
    app.include_router(router)

    async def override(request: Request):  # pragma: no cover - dependency hook
        return container

    app.dependency_overrides[routes_module.get_container] = override
    monkeypatch.setattr(routes_module, "get_settings", lambda: SimpleNamespace(review_secret="secret"))
    client = TestClient(app)
    return client, container


def test_create_and_list_analyses_contract(api_client):
    client, container = api_client
    payload = {
        "email": "user@example.com",
        "cvDocId": "doc-123",
        "jobDescription": "JD",
        "preferredYoutubeChannels": [],
    }
    resp = client.post("/v1/analyses", json=payload)
    assert resp.status_code == 200
    AnalysisResponse.model_validate(resp.json())

    listing = client.get("/v1/analyses")
    assert listing.status_code == 200
    data = AnalysisListResponse.model_validate(listing.json())
    assert any(item.analysisId.startswith("run-") for item in data.items)

    state_resp = client.get(f"/v1/analyses/{data.items[0].analysisId}")
    AnalysisStatusResponse.model_validate(state_resp.json())


def test_artifact_listing_and_schema_validation(api_client):
    client, container = api_client
    resp = client.get("/v1/analyses/seed/artifacts")
    assert resp.status_code == 200
    artifacts = [AnalysisArtifact.model_validate(item) for item in resp.json()]
    assert artifacts[0].analysisId == "seed"


def test_google_oauth_flow_and_review_approval(api_client):
    client, container = api_client

    start = client.get("/oauth/google/start", follow_redirects=False)
    assert start.status_code == 307
    assert start.headers["location"] == "https://accounts.test/auth"
    assert any(key.endswith("state-token") for key in container.cache.values)

    callback = client.get("/oauth/google/callback", params={"code": "abc", "state": "state-token"})
    assert callback.status_code == 200
    assert container.token_store.saved

    serializer = routes_module.URLSafeSerializer("secret", salt="approval")
    container.storage.records["seed"].status = AnalysisStatus.AWAITING_APPROVAL
    token = serializer.dumps({"analysis_id": "seed"})
    approve = client.post("/review/approve", json={"analysisId": "seed", "token": token})
    assert approve.status_code == 200
    assert container.runner.resume_calls == ["seed"]
