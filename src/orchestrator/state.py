"""LangGraph state + dependency containers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TypedDict

from app.config import Settings
from app.schemas import (
    AnalysisStatus,
    CvAnalysisLLMResponse,
    CvScoreLLMResponse,
    ImprovementPlan,
    MvpProject,
    ProjectSuggestion,
)
from services.gmail import GmailService
from services.google_docs import GoogleDocsService
from services.google_drive import GoogleDriveService
from services.gemini import GeminiService
from services.llm import LLMService
from services.ranking import RankingService
from services.storage import StorageService
from services.youtube import YouTubeService


class SkillQuery(TypedDict):
    """Represents a missing skill search payload."""

    skill: str
    query: str


class GraphState(TypedDict, total=False):
    """State passed between LangGraph nodes."""

    analysis_id: str
    email: str
    cv_doc_id: str
    job_description: str
    job_description_url: Optional[str]
    cv_text: str
    jd_text: str
    cv_analysis: CvAnalysisLLMResponse
    score: CvScoreLLMResponse
    improvements: ImprovementPlan
    skill_queries: list[SkillQuery]
    project_suggestions: list[ProjectSuggestion]
    mvp_projects: list[MvpProject]
    awaiting_approval: bool
    approval_token: str
    approval_granted: bool


@dataclass
class NodeDeps:
    """Dependencies injected into node functions."""

    settings: Settings
    storage: StorageService
    drive: GoogleDriveService
    docs: GoogleDocsService
    gmail: GmailService
    llm: LLMService
    ranking: RankingService
    youtube: Optional[YouTubeService]
    gemini: Optional[GeminiService]
