"""Generates MVP project plans that combine multiple missing skills."""
from __future__ import annotations

import logging
from typing import List

from orchestrator.state import GraphState, NodeDeps

logger = logging.getLogger(__name__)


def build_node(deps: NodeDeps):
    async def generate_mvp(state: GraphState) -> GraphState:
        if state.get("mvp_projects"):
            logger.debug("analysis %s MVP projects already generated", state["analysis_id"])
            return state

        score_model = state.get("score")
        analysis_model = state.get("cv_analysis")
        missing = list(dict.fromkeys(score_model.missingHardSkills if score_model else []))
        if not missing and analysis_model:
            missing = analysis_model.hardSkills[:5]
        missing = missing[:8]

        suggestions = state.get("project_suggestions", [])
        tutorial_catalog: List[dict[str, str]] = []
        for suggestion in suggestions:
            skill_name = getattr(suggestion, "skill", None) or suggestion.get("skill")
            projects = getattr(suggestion, "projects", None) or suggestion.get("projects") or []
            for project in projects[:3]:
                title = getattr(project, "tutorialTitle", None) or project.get("tutorialTitle")
                url = getattr(project, "tutorialUrl", None) or project.get("tutorialUrl")
                tip = getattr(project, "personalizationTip", None) or project.get("personalizationTip")
                tutorial_catalog.append(
                    {
                        "skill": skill_name,
                        "tutorialTitle": title,
                        "tutorialUrl": str(url),
                        "personalizationTip": tip,
                    }
                )

        if not missing or not tutorial_catalog:
            logger.info("analysis %s skipping MVP generation; insufficient data", state["analysis_id"])
            state["mvp_projects"] = []
            return state

        logger.info("analysis %s generating MVP projects", state["analysis_id"])
        try:
            projects = await deps.llm.generate_mvp_projects(
                missing_skills=missing,
                tutorial_catalog=tutorial_catalog,
                cv_text=state.get("cv_text", ""),
                jd_text=state.get("jd_text", ""),
            )
        except Exception:
            logger.exception("analysis %s failed to generate MVP projects", state["analysis_id"])
            projects = []

        state["mvp_projects"] = projects
        if projects:
            await deps.storage.save_artifact(
                state["analysis_id"],
                "mvp_projects",
                [proj.model_dump(mode="json") for proj in projects],
            )
        return state

    return generate_mvp
