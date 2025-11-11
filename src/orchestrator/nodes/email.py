"""Sends approval email with review link."""
from __future__ import annotations

import logging
from typing import Iterable

from itsdangerous import URLSafeSerializer

from app.schemas import AnalysisStatus, CvAnalysisLLMResponse
from orchestrator.state import GraphState, NodeDeps

logger = logging.getLogger(__name__)


def _first_non_empty(values: Iterable[str]) -> str:
    for value in values or []:
        stripped = value.strip()
        if stripped:
            return stripped
    return ""


def build_node(deps: NodeDeps):
    serializer = URLSafeSerializer(deps.settings.review_secret, salt="approval")

    async def send_email(state: GraphState) -> GraphState:
        if state.get("awaiting_approval") and state.get("approval_token"):
            logger.debug("analysis %s approval email already sent", state["analysis_id"])
            return state
        token = serializer.dumps({"analysis_id": state["analysis_id"]})
        review_url = (
            f"{deps.settings.frontend_base_url}/review/approve?"
            f"analysisId={state['analysis_id']}&token={token}"
        )
        score_model = state.get("score")
        analysis_model: CvAnalysisLLMResponse | None = state.get("cv_analysis")
        improvements = state.get("improvements")
        project_suggestions = state.get("project_suggestions", [])
        company_name = _first_non_empty(analysis_model.companyName) if analysis_model else ""
        job_title = _first_non_empty(analysis_model.jobTitle) if analysis_model else ""
        pieces = ["CV Analysis Ready"]
        if job_title and company_name:
            pieces.append(f"{job_title} at {company_name}")
        elif job_title:
            pieces.append(job_title)
        elif company_name:
            pieces.append(company_name)
        subject = " - ".join(pieces)
        scores_context = {
            "overallScore": score_model.overallScore if score_model else 0,
            "hardSkillsScore": score_model.hardSkillsScore if score_model else 0,
            "softSkillsScore": score_model.softSkillsScore if score_model else 0,
            "criticalReqScore": score_model.criticalReqScore if score_model and score_model.criticalReqScore is not None else 0,
        }
        doc_url = f"https://docs.google.com/document/d/{state['cv_doc_id']}/edit"
        html = deps.gmail.render(
            "email/approval.html.j2",
            analysisId=state["analysis_id"],
            reviewUrl=review_url,
            companyName=company_name,
            jobTitle=job_title,
            userEmail=state["email"],
            docUrl=doc_url,
            scores=scores_context,
            scoreModel=score_model,
            analysisModel=analysis_model,
            improvements=improvements,
            projectSuggestions=project_suggestions,
            mvpProjects=state.get("mvp_projects", []),
        )
        logger.info("analysis %s sending approval email to %s", state["analysis_id"], state["email"])
        await deps.gmail.send_html(
            state["email"],
            subject,
            html,
        )
        state["awaiting_approval"] = True
        state["approval_token"] = token
        await deps.storage.set_approval_token(state["analysis_id"], token)
        payload = {
            "cvAnalysis": analysis_model.model_dump() if analysis_model else None,
            "score": score_model.model_dump() if score_model else None,
            "projectSuggestions": [s.model_dump() for s in project_suggestions],
            "mvpProjects": [p.model_dump() for p in state.get("mvp_projects", [])],
        }
        await deps.storage.update_status(state["analysis_id"], AnalysisStatus.AWAITING_APPROVAL, payload)
        logger.info("analysis %s awaiting approval", state["analysis_id"])
        return state

    return send_email
