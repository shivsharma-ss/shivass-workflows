"""Collects tutorials per missing skill."""
from __future__ import annotations

import logging
from typing import List, Optional

from app.schemas import ProjectSuggestion, TutorialAnalysis, TutorialSuggestion
from orchestrator.state import GraphState, NodeDeps, SkillQuery
from services.youtube import YouTubeVideo

logger = logging.getLogger(__name__)


def build_node(deps: NodeDeps):
    async def yt_branch(state: GraphState) -> GraphState:
        suggestions: List[ProjectSuggestion] = []
        queries = state.get("skill_queries", [])
        if not deps.youtube:
            logger.warning("analysis %s skipping YouTube branch; no API key configured", state["analysis_id"])
            state["project_suggestions"] = []
            return state
        for item in queries:
            query = SkillQuery(skill=item["skill"], query=item["query"])
            logger.info(
                "analysis %s searching videos for skill '%s'",
                state["analysis_id"],
                query["skill"],
            )
            videos = await deps.youtube.search_tutorials(query=query["query"], max_results=8)
            top_videos = deps.ranking.top_videos(videos, limit=3)
            tutorials = []
            for video in top_videos:
                analysis_model: Optional[TutorialAnalysis] = None
                if deps.gemini:
                    gemini_result = await deps.gemini.analyze_video(video.url)
                    if gemini_result:
                        analysis_model = TutorialAnalysis(
                            summary=gemini_result.summary,
                            keyPoints=gemini_result.key_points,
                            difficultyLevel=gemini_result.difficulty_level,
                            prerequisites=gemini_result.prerequisites,
                            practicalTakeaways=gemini_result.practical_takeaways,
                        )
                tutorials.append(
                    TutorialSuggestion(
                        tutorialTitle=video.title,
                        tutorialUrl=video.url,
                        personalizationTip=_personalization_tip(query["skill"], video),
                        analysis=analysis_model,
                    )
                )
            suggestion = ProjectSuggestion(skill=query["skill"], projects=tutorials)
            suggestions.append(suggestion)
            logger.info(
                "analysis %s found %d tutorials for %s",
                state["analysis_id"],
                len(tutorials),
                query["skill"],
            )
        state["project_suggestions"] = suggestions
        await deps.storage.save_artifact(
            state["analysis_id"],
            "project_suggestions",
            [s.model_dump() for s in suggestions],
        )
        return state

    return yt_branch


def _personalization_tip(skill: str, video: YouTubeVideo) -> str:
    return (
        f"Build a highlight around {skill} referencing {video.channel_title}; "
        f"cite metrics from the tutorial to prove hands-on experience."
    )
