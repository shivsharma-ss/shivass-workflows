"""Collects tutorials per missing skill."""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from app.schemas import ProjectSuggestion, TutorialAnalysis, TutorialSuggestion
from orchestrator.state import GraphState, NodeDeps, SkillQuery
from orchestrator.utils import instrument_node
from services.channel_defaults import clone_default_channel_list
from services.youtube import YouTubeVideo

logger = logging.getLogger(__name__)


def build_node(deps: NodeDeps):
    async def yt_branch(state: GraphState) -> GraphState:
        suggestions: List[ProjectSuggestion] = []
        ranked_payload: list[dict[str, object]] = []
        queries = state.get("skill_queries", [])
        if not deps.youtube:
            logger.warning("analysis %s skipping YouTube branch; no API key configured", state["analysis_id"])
            state["project_suggestions"] = []
            return state
        preferred_channels = state.get("preferred_channels")
        if preferred_channels is None:
            preferred_channels = clone_default_channel_list()
            state["preferred_channels"] = preferred_channels
        user_channel_boosts = _preferred_channel_map(preferred_channels)
        for item in queries:
            query = SkillQuery(skill=item["skill"], query=item["query"])
            logger.info(
                "analysis %s searching videos for skill '%s'",
                state["analysis_id"],
                query["skill"],
            )
            videos = await deps.youtube.search_tutorials(query=query["query"], max_results=8)
            ranked_videos = deps.ranking.ranked_videos(
                videos,
                limit=3,
                skill_name=query["skill"],
                user_channel_boosts=user_channel_boosts,
            )
            tutorials = []
            skill_rankings: list[dict[str, object]] = []
            for rank, ranked in enumerate(ranked_videos, start=1):
                video = ranked.video
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
                if not analysis_model:
                    metadata = await deps.storage.get_youtube_video_metadata(video.url)
                    analysis_model = _analysis_from_metadata(metadata)
                tip = _personalization_tip(query["skill"], video)
                tutorials.append(
                    TutorialSuggestion(
                        tutorialTitle=video.title,
                        tutorialUrl=video.url,
                        personalizationTip=tip,
                        analysis=analysis_model,
                    )
                )
                skill_rankings.append(
                    {
                        "rank": rank,
                        "score": ranked.score,
                        "videoId": video.video_id,
                        "title": video.title,
                        "url": video.url,
                        "channelTitle": video.channel_title,
                        "duration": video.duration,
                        "viewCount": video.view_count,
                        "likeCount": video.like_count,
                        "commentCount": video.comment_count,
                        "publishedAt": video.published_at,
                        "personalizationTip": tip,
                        "analysis": analysis_model.model_dump(mode="json") if analysis_model else None,
                    }
                )
            suggestion = ProjectSuggestion(skill=query["skill"], projects=tutorials)
            suggestions.append(suggestion)
            if skill_rankings:
                ranked_payload.append(
                    {
                        "skill": query["skill"],
                        "videos": skill_rankings,
                    }
                )
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
        if ranked_payload:
            await deps.storage.save_artifact(
                state["analysis_id"],
                "video_rankings",
                ranked_payload,
            )
        return state

    return instrument_node("yt_branch", deps, yt_branch)


def _personalization_tip(skill: str, video: YouTubeVideo) -> str:
    return (
        f"Build a highlight around {skill} referencing {video.channel_title}; "
        f"cite metrics from the tutorial to prove hands-on experience."
    )


def _preferred_channel_map(entries) -> dict[str, float]:
    mapping: dict[str, float] = {}
    if not entries:
        return mapping
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw_name = entry.get("name", "")
        raw_boost = entry.get("boost", 1.0)
        name = str(raw_name).strip().lower()
        if not name:
            continue
        try:
            boost = float(raw_boost)
        except (TypeError, ValueError):
            continue
        if boost <= 0:
            continue
        mapping[name] = boost
    return mapping


def _analysis_from_metadata(metadata: Optional[dict[str, Any]]) -> Optional[TutorialAnalysis]:
    if not metadata:
        return None
    if not (
        metadata.get("key_points")
        or metadata.get("prerequisites")
        or metadata.get("takeaways")
        or metadata.get("difficulty_level")
    ):
        return None
    return TutorialAnalysis(
        summary=str(metadata.get("summary") or "").strip(),
        keyPoints=[str(item).strip() for item in metadata.get("key_points", []) if str(item).strip()],
        difficultyLevel=str(metadata.get("difficulty_level") or "").strip(),
        prerequisites=[str(item).strip() for item in metadata.get("prerequisites", []) if str(item).strip()],
        practicalTakeaways=[str(item).strip() for item in metadata.get("takeaways", []) if str(item).strip()],
    )
