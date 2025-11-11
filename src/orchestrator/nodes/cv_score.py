"""Scores CV and builds improvement plan."""
from __future__ import annotations

import logging

from orchestrator.state import GraphState, NodeDeps

logger = logging.getLogger(__name__)


def build_node(deps: NodeDeps):
    async def cv_score(state: GraphState) -> GraphState:
        if state.get("score") and state.get("improvements"):
            logger.debug("analysis %s skipping scoring; already available", state["analysis_id"])
            return state
        logger.info("analysis %s scoring CV", state["analysis_id"])
        score = await deps.llm.score_cv(
            state["cv_text"],
            state["jd_text"],
            state.get("cv_analysis"),
        )
        improvements = await deps.llm.improvement_plan(
            state["cv_text"],
            state["jd_text"],
            score,
        )
        state["score"] = score
        state["improvements"] = improvements
        await deps.storage.save_artifact(state["analysis_id"], "cv_score", score.model_dump())
        await deps.storage.save_artifact(state["analysis_id"], "cv_improvements", improvements.model_dump())
        logger.info("analysis %s scoring complete (overall=%s)", state["analysis_id"], score.overallScore)
        return state

    return cv_score
