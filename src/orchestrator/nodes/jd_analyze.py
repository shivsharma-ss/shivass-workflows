"""LLM-powered JD vs CV analyzer."""
from __future__ import annotations

import logging

from orchestrator.state import GraphState, NodeDeps

logger = logging.getLogger(__name__)


def build_node(deps: NodeDeps):
    async def jd_analyze(state: GraphState) -> GraphState:
        if state.get("cv_analysis"):
            logger.debug("analysis %s skipping JD analysis; already present", state["analysis_id"])
            return state
        logger.info("analysis %s running JD analysis", state["analysis_id"])
        analysis = await deps.llm.analyze_alignment(state["cv_text"], state["jd_text"])
        state["cv_analysis"] = analysis
        await deps.storage.save_artifact(state["analysis_id"], "cv_analysis", analysis.model_dump())
        logger.info("analysis %s JD analysis complete", state["analysis_id"])
        return state

    return jd_analyze
