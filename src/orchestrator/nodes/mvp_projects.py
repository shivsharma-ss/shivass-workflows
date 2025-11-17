"""Generates MVP project plans that combine multiple missing skills."""
from __future__ import annotations

import logging
from typing import List

from orchestrator.state import GraphState, NodeDeps
from orchestrator.utils import instrument_node

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

        def _get(value, field):
            if value is None:
                return None
            if isinstance(value, dict):
                return value.get(field)
            return getattr(value, field, None)

        suggestions = state.get("project_suggestions", [])
        tutorial_catalog: List[dict[str, str]] = []
        for suggestion in suggestions or []:
            skill_name = _get(suggestion, "skill") or "general"
            projects = _get(suggestion, "projects") or []
            for project in list(projects)[:3]:
                title = _get(project, "tutorialTitle")
                url = _get(project, "tutorialUrl")
                tip = _get(project, "personalizationTip")
                if not url and not title:
                    continue
                tutorial_catalog.append(
                    {
                        "skill": skill_name,
                        "tutorialTitle": title,
                        "tutorialUrl": str(url) if url else "",
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

    return instrument_node("mvp_projects", deps, generate_mvp)
