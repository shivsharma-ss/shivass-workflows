"""End-to-end style tests that exercise the orchestrator runner with fake graphs."""

import asyncio
from dataclasses import dataclass
from typing import Any, Optional, cast

import pytest

from app.config import Settings
from app.schemas import AnalysisRequest, AnalysisStatus
from orchestrator.exceptions import ApprovalPendingError
from orchestrator.runner import OrchestratorRunner
from orchestrator.state import NodeDeps
from services.gmail import GmailService
from services.google_docs import GoogleDocsService
from services.google_drive import GoogleDriveService
from services.llm import LLMService
from services.ranking import RankingService
from services.storage import StorageService
from services.youtube import YouTubeService


@dataclass
class FakeGraph:
    """Test double that mimics LangGraph's ainvoke behavior."""

    result_state: Optional[dict[str, Any]] = None
    interrupt: bool = False

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        if self.interrupt:
            raise ApprovalPendingError(state["analysis_id"], state)
        return {**state, **(self.result_state or {})}


class DummyService:
    """Marker class used when a node dependency is not under test."""


async def make_deps(tmp_db: str):
    """Spin up lightweight dependencies backed by an on-disk sqlite database."""

    settings = Settings.model_validate(
        {
            "APP_ENV": "test",  # keeps config deterministic for assertions
            "OPENAI_API_KEY": "sk",  # dummy key; no API calls are made
            "GOOGLE_SERVICE_ACCOUNT_FILE": "service-account.json",  # placeholder path
            "GOOGLE_WORKSPACE_SUBJECT": None,
            "GMAIL_SENDER": "test@example.com",
            "SMTP_SERVER": "smtp",
            "SMTP_PORT": 587,
            "SMTP_USERNAME": None,
            "SMTP_PASSWORD": None,
            "REDIS_URL": "",
            "DATABASE_URL": tmp_db,
            "FRONTEND_BASE_URL": "http://localhost",
            "REVIEW_SECRET": "secret",
        }
    )
    storage = StorageService(tmp_db)
    await storage.initialize()
    # Provide minimal stubs to satisfy node dependencies without touching real APIs.
    node_deps = NodeDeps(
        settings=settings,
        storage=storage,
        drive=cast(GoogleDriveService, DummyService()),
        docs=cast(GoogleDocsService, DummyService()),
        gmail=cast(GmailService, DummyService()),
        llm=cast(LLMService, DummyService()),
        ranking=RankingService(),
        youtube=cast(Optional[YouTubeService], None),
        gemini=None,
    )
    return node_deps, storage, settings


@pytest.mark.asyncio
async def test_runner_handles_interrupt(tmp_path):
    """Runner should persist state and mark status awaiting approval when interrupted."""
    db_path = tmp_path / "interrupt.db"
    node_deps, storage, _ = await make_deps(f"sqlite+aiosqlite:///{db_path}")
    graph = FakeGraph(interrupt=True)
    runner = OrchestratorRunner(graph, node_deps)
    request = AnalysisRequest(
        email="user@example.com",
        cvDocId="doc",
        jobDescription="JD",
        jobDescriptionUrl=None,
    )
    analysis_id, status = await runner.kickoff(request, background=False)
    assert status == AnalysisStatus.AWAITING_APPROVAL
    record = await storage.get_analysis(analysis_id)
    # The DB snapshot should reflect a paused workflow.
    assert record is not None
    assert record.status == AnalysisStatus.AWAITING_APPROVAL


@pytest.mark.asyncio
async def test_runner_completes(tmp_path):
    """Happy path: runner persists completion payload when graph finishes."""
    db_path = tmp_path / "complete.db"
    node_deps, storage, _ = await make_deps(f"sqlite+aiosqlite:///{db_path}")
    graph = FakeGraph(result_state={"cv_text": "done"})
    runner = OrchestratorRunner(graph, node_deps)
    request = AnalysisRequest(
        email="user@example.com",
        cvDocId="doc",
        jobDescription="JD",
        jobDescriptionUrl=None,
    )
    analysis_id, status = await runner.kickoff(request, background=False)
    assert status == AnalysisStatus.COMPLETED
    record = await storage.get_analysis(analysis_id)
    # Final payload is persisted as COMPLETED so clients can read results.
    assert record is not None
    assert record.status == AnalysisStatus.COMPLETED
