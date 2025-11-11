"""Re-score CV after edits and send completion email."""
from __future__ import annotations

import logging

from app.schemas import AnalysisStatus
from orchestrator.state import GraphState, NodeDeps

logger = logging.getLogger(__name__)


def build_node(deps: NodeDeps):
    async def recalc(state: GraphState) -> GraphState:
        logger.info("analysis %s recalculating score after doc updates", state["analysis_id"])
        new_score = await deps.llm.score_cv(
            state["cv_text"],
            state["jd_text"],
            state.get("cv_analysis"),
        )
        state["score"] = new_score
        state["awaiting_approval"] = False
        doc_url = f"https://docs.google.com/document/d/{state['cv_doc_id']}/edit"
        html = deps.gmail.render(
            "email/completion.html.j2",
            analysisId=state["analysis_id"],
            scores={"overallScore": new_score.overallScore},
            docUrl=doc_url,
        )
        await deps.gmail.send_html(
            state["email"],
            "CV updates applied",
            html,
        )
        payload = {
            "cvAnalysis": state.get("cv_analysis").model_dump() if state.get("cv_analysis") else None,
            "score": new_score.model_dump(),
            "improvements": state.get("improvements").model_dump() if state.get("improvements") else None,
            "projectSuggestions": [s.model_dump() for s in state.get("project_suggestions", [])],
            "mvpProjects": [p.model_dump() for p in state.get("mvp_projects", [])],
        }
        await deps.storage.save_artifact(state["analysis_id"], "final_score", new_score.model_dump())
        await deps.storage.update_status(state["analysis_id"], AnalysisStatus.COMPLETED, payload)
        logger.info("analysis %s completed; final score=%s", state["analysis_id"], new_score.overallScore)
        return state

    return recalc
