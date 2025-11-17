"""Creates skill-specific YouTube search queries."""
from __future__ import annotations

import logging

from orchestrator.state import GraphState, NodeDeps
from orchestrator.utils import instrument_node

logger = logging.getLogger(__name__)


def build_node(deps: NodeDeps):
    async def build_queries(state: GraphState) -> GraphState:
        missing: list[str] = []
        score_model = state.get("score")
        if score_model:
            missing.extend(score_model.missingHardSkills)
        if not missing and state.get("cv_analysis"):
            analysis = state["cv_analysis"]
            missing.extend(analysis.hardSkills[:5])
        job_title = ""
        analysis = state.get("cv_analysis")
        if analysis:
            for title in analysis.jobTitle:
                title = title.strip()
                if title:
                    job_title = title
                    break
        skill_queries = [
            {
                "skill": skill,
                "query": f"{skill} tutorial project for {job_title or 'the role'}",
            }
            for skill in missing
        ] or [
            {"skill": "general", "query": "software engineering portfolio tutorial"}
        ]
        state["skill_queries"] = skill_queries
        logger.info(
            "analysis %s prepared %d skill queries",
            state["analysis_id"],
            len(skill_queries),
        )
        return state

    return instrument_node("build_queries", deps, build_queries)
