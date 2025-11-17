"""Exports CV text from Drive."""
from __future__ import annotations

import asyncio
import logging

from orchestrator.state import GraphState, NodeDeps
from orchestrator.utils import instrument_node

MAX_DOC_BYTES = 10 * 1024 * 1024

logger = logging.getLogger(__name__)


def build_node(deps: NodeDeps):
    async def drive_export(state: GraphState) -> GraphState:
        if state.get("cv_text"):
            logger.debug("analysis %s skipping CV export; already cached", state["analysis_id"])
            return state
        logger.info("analysis %s exporting CV doc %s", state["analysis_id"], state["cv_doc_id"])
        cv_text = await asyncio.to_thread(deps.drive.export_doc_text, state["cv_doc_id"])
        if len(cv_text.encode("utf-8")) > MAX_DOC_BYTES:
            raise ValueError("CV document exceeds 10 MB export limit")
        state["cv_text"] = cv_text
        await deps.storage.save_artifact(state["analysis_id"], "cv_text", cv_text)
        logger.info("analysis %s CV export complete (%d chars)", state["analysis_id"], len(cv_text))
        return state

    return instrument_node("drive_export", deps, drive_export)
