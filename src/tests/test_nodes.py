"""Unit tests for every LangGraph node using fake dependencies."""

from types import SimpleNamespace
from typing import Any

import pytest

from app.schemas import (
    AnalysisStatus,
    CvAnalysisLLMResponse,
    CvScoreLLMResponse,
    ImprovementAddition,
    ImprovementPlan,
    ImprovementRemoval,
    ImprovementReformulation,
    MvpProject,
    ProjectSuggestion,
    TutorialSuggestion,
)
from orchestrator.exceptions import ApprovalPendingError
from orchestrator.nodes import (
    build_queries,
    collect,
    cv_score,
    docs_apply,
    drive_export,
    email,
    ingest,
    jd_analyze,
    merge_jd,
    mvp_projects as mvp_node,
    recalc,
    wait_approval,
    yt_branch,
)
from orchestrator.state import GraphState, NodeDeps
from services.gemini import VideoAnalysis
from services.ranking import RankingService
from services.youtube import YouTubeVideo


class DummySettings:
    """Minimal settings bag to satisfy the NodeDeps contract."""

    review_secret = "secret-key"
    frontend_base_url = "https://frontend.test"


class FakeStorage:
    """Records status/token interactions for inspection."""

    def __init__(self):
        self.status_updates = []
        self.tokens = []
        self.artifacts: dict[tuple[str, str], Any] = {}
        self.youtube_cache: dict[str, Any] = {}
        self.oauth_credentials: dict[tuple[str, str], dict[str, Any]] = {}

    async def update_status(self, analysis_id, status, payload):
        self.status_updates.append({"analysis_id": analysis_id, "status": status, "payload": payload})

    async def set_approval_token(self, analysis_id, token):
        self.tokens.append((analysis_id, token))

    async def save_artifact(self, analysis_id, artifact_type, content):
        self.artifacts[(analysis_id, artifact_type)] = content

    async def get_artifact(self, analysis_id, artifact_type):
        return self.artifacts.get((analysis_id, artifact_type))

    async def save_youtube_cache(self, query, videos):
        self.youtube_cache[query] = videos

    async def get_youtube_cache(self, query, max_age_seconds=86400):
        return self.youtube_cache.get(query)

    async def save_youtube_video_metadata(self, video_url, summary, skills, tech_stack):
        pass

    async def get_youtube_video_metadata(self, video_url):
        return None

    async def save_oauth_credentials(self, provider, account, credentials):
        self.oauth_credentials[(provider, account)] = credentials

    async def get_oauth_credentials(self, provider, account):
        return self.oauth_credentials.get((provider, account))


class FakeDrive:
    """Returns a canned CV export and records the requested doc id."""

    def __init__(self):
        self.calls = []

    def export_doc_text(self, doc_id):
        self.calls.append(doc_id)
        return "CV exported"


class FakeDocs:
    """Tracks text inserted into Docs without real API calls."""

    def __init__(self):
        self.calls = []

    def prepend_text(self, doc_id, text):
        self.calls.append((doc_id, text))


class FakeGmail:
    """Captures rendered templates and send attempts."""

    def __init__(self):
        self.render_calls = []
        self.sent = []

    def render(self, template, **context):
        self.render_calls.append((template, context))
        return "<html>body</html>"

    async def send_html(self, to_email, subject, html):
        self.sent.append((to_email, subject, html))
        return {"id": "1"}


class FakeLLM:
    """Supplies predetermined LLM outputs for analysis/score/improvements."""

    def __init__(self, analysis, score, improvements, mvp_plan):
        self.analysis = analysis
        self.score = score
        self.improvements = improvements
        self.mvp_plan = mvp_plan
        self.score_calls = 0

    async def analyze_alignment(self, cv_text, jd_text):
        return self.analysis

    async def score_cv(self, cv_text, jd_text, required=None):
        self.score_calls += 1
        return self.score

    async def improvement_plan(self, cv_text, jd_text, score):
        return self.improvements

    async def generate_mvp_projects(self, missing_skills, tutorial_catalog, cv_text, jd_text):
        return self.mvp_plan


class FakeYouTube:
    """Produces deterministic video search results for a skill query."""

    def __init__(self):
        self.queries = []

    async def search_tutorials(self, query, max_results=10):
        self.queries.append(query)
        return [
            YouTubeVideo(
                video_id="vid1",
                title="Tutorial",
                description="",
                url="https://youtu.be/vid1",
                channel_title="Channel",
                duration="PT15M",
                view_count=5000,
                like_count=300,
            )
        ]


class FakeGemini:
    """Returns canned analysis payloads."""

    def __init__(self):
        self.calls = []

    async def analyze_video(self, url: str):
        self.calls.append(url)
        return VideoAnalysis(
            summary="Summary",
            key_points=["Key insight"],
            difficulty_level="Intermediate",
            prerequisites=["Python"],
            practical_takeaways=["Ship a small agent"],
        )


@pytest.fixture
def improvements_model():
    """Reusable ImprovementPlan stub for nodes requiring suggestions."""
    return ImprovementPlan(
        reformulations=[
            ImprovementReformulation(original="Old", improved="New", reason="Clearer"),
        ],
        removals=[
            ImprovementRemoval(text="Remove", reason="Irrelevant", alternative=""),
        ],
        additions=[
            ImprovementAddition(section="Summary", content="Updated", reason="Align"),
        ],
    )


@pytest.fixture
def analysis_model():
    """Structured alignment output used across nodes."""
    return CvAnalysisLLMResponse(
        companyName=["AI Corp"],
        jobTitle=["Data Scientist"],
        hardSkills=["Python", "TensorFlow", "SQL"],
        softSkills=["Teamwork", "Communication"],
        criticalRequirements=["German C1"],
    )


@pytest.fixture
def score_model():
    """Structured scoring output with missing skills populated."""
    return CvScoreLLMResponse(
        overallScore=70,
        hardSkillsScore=65,
        softSkillsScore=75,
        matchedHardSkills=["Python"],
        matchedSoftSkills=["Teamwork"],
        missingHardSkills=["TensorFlow"],
        missingSoftSkills=["Stakeholder communication"],
        strengths=["Python automation experience"],
        weaknesses=["No TensorFlow evidence"],
        criticalReqScore=50,
    )


@pytest.fixture
def mvp_projects_fixture():
    """Sample MVP project plans."""
    return [
        MvpProject(
            tutorialTitle="Tutorial",
            tutorialUrl="https://youtu.be/demo",
            skillsCombined=["TensorFlow", "Docker", "MySQL"],
            personalizationTip="Containerize the inference API with the CV stack.",
            cvBlurb="Built an AI inference API with TensorFlow + Docker, exposing REST endpoints and MySQL persistence.",
            estimatedBuildTime="2 weekends",
            roleFitNote="Shows readiness to ship agentic SaaS workflows.",
        )
    ]


@pytest.fixture
def node_env(analysis_model, score_model, improvements_model, mvp_projects_fixture):
    """Bundle fake dependencies so each test can focus on the node logic."""
    storage = FakeStorage()
    drive = FakeDrive()
    docs = FakeDocs()
    gmail = FakeGmail()
    llm = FakeLLM(analysis_model, score_model, improvements_model, mvp_projects_fixture)
    youtube = FakeYouTube()
    deps = NodeDeps(
        settings=DummySettings(),
        storage=storage,
        drive=drive,
        docs=docs,
        gmail=gmail,
        llm=llm,
        ranking=RankingService(),
        youtube=youtube,
        gemini=None,
    )
    return SimpleNamespace(
        deps=deps,
        storage=storage,
        drive=drive,
        docs=docs,
        gmail=gmail,
        llm=llm,
        youtube=youtube,
    )


@pytest.fixture
def base_state(analysis_model, score_model, improvements_model) -> GraphState:
    """Base LangGraph state representing a run mid-flight."""
    return {
        "analysis_id": "analysis-1",
        "email": "user@example.com",
        "cv_doc_id": "doc123",
        "job_description": "JD",
        "job_description_url": None,
        "cv_text": "Resume text",
        "jd_text": "Job text",
        "cv_analysis": analysis_model,
        "score": score_model,
        "improvements": improvements_model,
        "project_suggestions": [
            ProjectSuggestion(
                skill="TensorFlow",
                projects=[
                    TutorialSuggestion(
                        tutorialTitle="TF Tutorial",
                        tutorialUrl="https://youtu.be/vid",
                        personalizationTip="Build an inference service",
                    )
                ],
            )
        ],
        "mvp_projects": [],
    }


@pytest.mark.asyncio
async def test_ingest_marks_run(node_env, base_state):
    """Ingest should mark status RUNNING and seed project lists."""
    node = ingest.build_node(node_env.deps)
    result = await node(base_state.copy())
    assert node_env.storage.status_updates[-1]["status"] == AnalysisStatus.RUNNING
    assert result["project_suggestions"] == []


@pytest.mark.asyncio
async def test_drive_export_fetches_text(node_env, base_state):
    """Drive export should fetch once and populate cv_text in state."""
    node = drive_export.build_node(node_env.deps)
    state = base_state.copy()
    state.pop("cv_text")
    result = await node(state)
    assert result["cv_text"] == "CV exported"
    assert node_env.drive.calls == ["doc123"]


@pytest.mark.asyncio
async def test_merge_jd_keeps_inline(node_env, base_state):
    """If inline JD text exists, merge_jd should keep it unchanged."""
    node = merge_jd.build_node(node_env.deps)
    result = await node(base_state.copy())
    assert result["jd_text"] == "JD"


@pytest.mark.asyncio
async def test_jd_analyze_sets_model(node_env, base_state):
    """Node should call LLM once and store CvAnalysisLLMResponse."""
    node = jd_analyze.build_node(node_env.deps)
    state = base_state.copy()
    state.pop("cv_analysis")
    result = await node(state)
    assert result["cv_analysis"].jobTitle[0] == "Data Scientist"


@pytest.mark.asyncio
async def test_cv_score_populates_scores(node_env, base_state):
    """cv_score node should populate both score + improvements payloads."""
    node = cv_score.build_node(node_env.deps)
    state = base_state.copy()
    state.pop("score")
    state.pop("improvements")
    result = await node(state)
    assert result["score"].overallScore == 70
    assert result["improvements"].reformulations


@pytest.mark.asyncio
async def test_build_queries_from_missing_skills(node_env, base_state):
    """build_queries should derive search payloads from missing skills."""
    node = build_queries.build_node(node_env.deps)
    result = await node(base_state.copy())
    assert result["skill_queries"][0]["skill"] == "TensorFlow"


@pytest.mark.asyncio
async def test_yt_branch_creates_suggestions(node_env, base_state):
    """yt_branch should request tutorials per skill and persist suggestions."""
    state = base_state.copy()
    state["skill_queries"] = [{"skill": "TensorFlow", "query": "TensorFlow tutorial"}]
    node = yt_branch.build_node(node_env.deps)
    result = await node(state)
    assert result["project_suggestions"][0].projects[0].tutorialTitle == "Tutorial"
    assert node_env.youtube.queries == ["TensorFlow tutorial"]


@pytest.mark.asyncio
async def test_yt_branch_includes_gemini_analysis(node_env, base_state):
    """When Gemini is configured, tutorial analysis data should be attached."""
    state = base_state.copy()
    state["skill_queries"] = [{"skill": "TensorFlow", "query": "TensorFlow tutorial"}]
    gemini = FakeGemini()
    deps = NodeDeps(
        settings=node_env.deps.settings,
        storage=node_env.storage,
        drive=node_env.drive,
        docs=node_env.docs,
        gmail=node_env.gmail,
        llm=node_env.llm,
        ranking=node_env.deps.ranking,
        youtube=node_env.youtube,
        gemini=gemini,
    )
    node = yt_branch.build_node(deps)
    result = await node(state)
    analysis = result["project_suggestions"][0].projects[0].analysis
    assert analysis is not None
    assert analysis.summary == "Summary"
    assert gemini.calls == ["https://youtu.be/vid1"]


@pytest.mark.asyncio
async def test_collect_keeps_existing_list(node_env, base_state):
    """collect is a barrier node that simply guarantees the list exists."""
    state = base_state.copy()
    state["project_suggestions"] = []
    node = collect.build_node(node_env.deps)
    result = await node(state)
    assert "project_suggestions" in result


@pytest.mark.asyncio
async def test_mvp_projects_node_generates_projects(node_env, base_state):
    """MVP node should invoke LLM and persist artifact."""
    node = mvp_node.build_node(node_env.deps)
    result = await node(base_state.copy())
    assert result["mvp_projects"]
    assert ("analysis-1", "mvp_projects") in node_env.storage.artifacts


@pytest.mark.asyncio
async def test_email_sends_and_sets_token(node_env, base_state):
    """Email node should render template, send, and persist approval token."""
    node = email.build_node(node_env.deps)
    result = await node(base_state.copy())
    assert result["awaiting_approval"] is True
    assert node_env.storage.tokens
    assert node_env.gmail.sent


@pytest.mark.asyncio
async def test_wait_approval_flags_state(node_env, base_state):
    """wait_approval should simply flip awaiting flag."""
    node = wait_approval.build_node(node_env.deps)
    result = await node(base_state.copy())
    assert result["awaiting_approval"] is True


@pytest.mark.asyncio
async def test_docs_apply_requires_approval(node_env, base_state):
    """Without approval flag, docs_apply should raise the custom pause error."""
    node = docs_apply.build_node(node_env.deps)
    with pytest.raises(ApprovalPendingError):
        await node(base_state.copy())


@pytest.mark.asyncio
async def test_docs_apply_prepends_when_approved(node_env, base_state):
    """Once approved, docs_apply prepends improvements and updates cv_text."""
    node = docs_apply.build_node(node_env.deps)
    state = base_state.copy()
    state["approval_granted"] = True
    result = await node(state)
    assert node_env.docs.calls
    assert result["cv_text"].startswith("CV Alignment Suggestions")


@pytest.mark.asyncio
async def test_recalc_updates_status_and_email(node_env, base_state):
    """recalc should re-score, send completion email, and mark status complete."""
    node = recalc.build_node(node_env.deps)
    result = await node(base_state.copy())
    assert node_env.gmail.sent
    assert node_env.storage.status_updates[-1]["status"] == AnalysisStatus.COMPLETED
    assert result["score"].overallScore == 70
