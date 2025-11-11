"""Pydantic schemas for HTTP payloads and LLM structured outputs."""
from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import AliasChoices, BaseModel, Field, HttpUrl, field_serializer


class AnalysisStatus(str, Enum):
    """Possible lifecycle states for an analysis run."""

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisRequest(BaseModel):
    """Payload accepted by POST /v1/analyses."""

    email: str = Field(
        ...,
        description="User email to notify",
        validation_alias=AliasChoices("email", "userEmail"),
    )
    cvDocId: str = Field(..., description="Google Docs document ID for the CV")
    jobDescription: Optional[str] = Field(default=None, description="Inline job description text")
    jobDescriptionUrl: Optional[HttpUrl] = Field(default=None, description="URL to fetch the job description")

    model_config = {"populate_by_name": True}


class AnalysisResponse(BaseModel):
    """Minimal acknowledgement for analysis kickoff."""

    analysisId: str
    status: AnalysisStatus


class AnalysisStatusResponse(BaseModel):
    """Snapshot of run progress."""

    analysisId: str
    status: AnalysisStatus
    lastError: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AnalysisSummary(BaseModel):
    """Compact run summary used by dashboards."""

    analysisId: str
    email: str
    cvDocId: str
    status: AnalysisStatus
    lastError: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime

    model_config = {"populate_by_name": True}

    @field_serializer("createdAt", "updatedAt")
    def serialize_dt(self, value: datetime) -> str:
        return value.isoformat()


class AnalysisListResponse(BaseModel):
    """Paginated list wrapper for analyses."""

    items: list[AnalysisSummary] = Field(default_factory=list)


class AnalysisArtifact(BaseModel):
    """Artifact payload returned by the API."""

    analysisId: str
    artifactType: str
    content: str
    createdAt: datetime

    model_config = {"populate_by_name": True}

    @field_serializer("createdAt")
    def serialize_created_at(self, value: datetime) -> str:
        return value.isoformat()


class ApprovalRequest(BaseModel):
    """Payload used by reviewers to approve changes."""

    analysisId: str
    token: str


def _alias_choices(field_name: str) -> AliasChoices:
    """Return alias choices that accept camelCase and snake_case variants."""

    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", field_name).lower()
    return AliasChoices(field_name, snake)


class CvAnalysisLLMResponse(BaseModel):
    """Job description extraction used to guide downstream scoring."""

    companyName: list[str] = Field(..., validation_alias=_alias_choices("companyName"))
    jobTitle: list[str] = Field(..., validation_alias=_alias_choices("jobTitle"))
    hardSkills: list[str] = Field(..., validation_alias=_alias_choices("hardSkills"))
    softSkills: list[str] = Field(..., validation_alias=_alias_choices("softSkills"))
    criticalRequirements: list[str] = Field(..., validation_alias=_alias_choices("criticalRequirements"))

    model_config = {"populate_by_name": True}


class CvScoreLLMResponse(BaseModel):
    """Structured scoring response for the CV."""

    overallScore: int = Field(ge=0, le=100, validation_alias=_alias_choices("overallScore"))
    hardSkillsScore: int = Field(ge=0, le=100, validation_alias=_alias_choices("hardSkillsScore"))
    softSkillsScore: int = Field(ge=0, le=100, validation_alias=_alias_choices("softSkillsScore"))
    matchedHardSkills: list[str] = Field(..., validation_alias=_alias_choices("matchedHardSkills"))
    matchedSoftSkills: list[str] = Field(..., validation_alias=_alias_choices("matchedSoftSkills"))
    missingHardSkills: list[str] = Field(..., validation_alias=_alias_choices("missingHardSkills"))
    missingSoftSkills: list[str] = Field(..., validation_alias=_alias_choices("missingSoftSkills"))
    strengths: list[str] = Field(..., validation_alias=_alias_choices("strengths"))
    weaknesses: list[str] = Field(..., validation_alias=_alias_choices("weaknesses"))
    criticalReqScore: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        validation_alias=_alias_choices("criticalReqScore"),
    )

    model_config = {"populate_by_name": True}


class ImprovementReformulation(BaseModel):
    original: str = Field(..., validation_alias=_alias_choices("original"))
    improved: str = Field(..., validation_alias=_alias_choices("improved"))
    reason: str = Field(..., validation_alias=_alias_choices("reason"))


class ImprovementRemoval(BaseModel):
    text: str = Field(..., validation_alias=_alias_choices("text"))
    reason: str = Field(..., validation_alias=_alias_choices("reason"))
    alternative: str = Field(..., validation_alias=_alias_choices("alternative"))


class ImprovementAddition(BaseModel):
    section: str = Field(..., validation_alias=_alias_choices("section"))
    content: str = Field(..., validation_alias=_alias_choices("content"))
    reason: str = Field(..., validation_alias=_alias_choices("reason"))


class ImprovementPlan(BaseModel):
    """LLM response describing concrete CV edits."""

    reformulations: list[ImprovementReformulation] = Field(
        ..., validation_alias=_alias_choices("reformulations")
    )
    removals: list[ImprovementRemoval] = Field(..., validation_alias=_alias_choices("removals"))
    additions: list[ImprovementAddition] = Field(..., validation_alias=_alias_choices("additions"))

    model_config = {"populate_by_name": True}


class TutorialSuggestion(BaseModel):
    tutorialTitle: str = Field(..., validation_alias=_alias_choices("tutorialTitle"))
    tutorialUrl: HttpUrl = Field(..., validation_alias=_alias_choices("tutorialUrl"))
    personalizationTip: str = Field(..., validation_alias=_alias_choices("personalizationTip"))
    analysis: Optional["TutorialAnalysis"] = Field(default=None, validation_alias=_alias_choices("analysis"))

    model_config = {"populate_by_name": True}
    
    @field_serializer('tutorialUrl')
    def serialize_url(self, url: HttpUrl) -> str:
        return str(url)


class TutorialAnalysis(BaseModel):
    summary: str = Field(..., description="Brief summary of the tutorial")
    keyPoints: list[str] = Field(..., description="Key learning points", validation_alias=_alias_choices("keyPoints"))
    difficultyLevel: str = Field(..., description="Estimated difficulty level", validation_alias=_alias_choices("difficultyLevel"))
    prerequisites: list[str] = Field(..., description="Required prerequisites", validation_alias=_alias_choices("prerequisites"))
    practicalTakeaways: list[str] = Field(
        ..., description="Practical implementation insights", validation_alias=_alias_choices("practicalTakeaways")
    )

    model_config = {"populate_by_name": True}


class ProjectSuggestion(BaseModel):
    skill: str = Field(..., validation_alias=_alias_choices("skill"))
    projects: list[TutorialSuggestion] = Field(..., validation_alias=_alias_choices("projects"))

    model_config = {"populate_by_name": True}


class MvpProject(BaseModel):
    tutorialTitle: str = Field(..., validation_alias=_alias_choices("tutorialTitle"))
    tutorialUrl: HttpUrl = Field(..., validation_alias=_alias_choices("tutorialUrl"))
    skillsCombined: list[str] = Field(..., validation_alias=_alias_choices("skillsCombined"))
    personalizationTip: str = Field(..., validation_alias=_alias_choices("personalizationTip"))
    cvBlurb: str = Field(..., validation_alias=_alias_choices("cvBlurb"))
    estimatedBuildTime: str = Field(..., validation_alias=_alias_choices("estimatedBuildTime"))
    roleFitNote: str = Field(..., validation_alias=_alias_choices("roleFitNote"))

    model_config = {"populate_by_name": True}


class MvpPlan(BaseModel):
    mvpProjects: list[MvpProject]

    model_config = {"populate_by_name": True}


class GraphResult(BaseModel):
    """Snapshot stored after LangGraph execution completes."""

    analysisId: str
    email: str
    cvDocId: str
    cvAnalysis: Optional[CvAnalysisLLMResponse] = None
    score: Optional[CvScoreLLMResponse] = None
    improvements: Optional[ImprovementPlan] = None
    projectSuggestions: list[ProjectSuggestion] = Field(default_factory=list)
    mvpProjects: list[MvpProject] = Field(default_factory=list)
    status: AnalysisStatus = AnalysisStatus.PENDING
