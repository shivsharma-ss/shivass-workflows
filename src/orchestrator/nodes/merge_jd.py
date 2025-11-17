"""Combines inline JD text with fetched URL."""
from __future__ import annotations

import logging

import httpx

from orchestrator.state import GraphState, NodeDeps
from orchestrator.utils import instrument_node

logger = logging.getLogger(__name__)


def build_node(deps: NodeDeps):
    async def merge_jd(state: GraphState) -> GraphState:
        logger.info("analysis %s merging JD sources", state["analysis_id"])
        jd_text = state.get("job_description", "").strip()
        if not jd_text and state.get("job_description_url"):
            logger.info(
                "analysis %s fetching JD from %s",
                state["analysis_id"],
                state["job_description_url"],
            )
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    state["job_description_url"],
                    headers={"User-Agent": "cv-jd-orchestrator"},
                )
                resp.raise_for_status()
                jd_text = resp.text
        if not jd_text:
            raise ValueError("No job description provided")
        state["jd_text"] = jd_text
        await deps.storage.save_artifact(state["analysis_id"], "jd_text", jd_text)
        logger.info(
            "analysis %s merged JD text (%d chars)",
            state["analysis_id"],
            len(jd_text),
        )
        return state

    return instrument_node("merge_jd", deps, merge_jd)
