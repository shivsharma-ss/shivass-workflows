"""Initial node to mark run as in-progress."""
from __future__ import annotations

import logging

from app.schemas import AnalysisStatus
from orchestrator.state import GraphState, NodeDeps

logger = logging.getLogger(__name__)


def build_node(deps: NodeDeps):
    """Return ingest node."""

    async def ingest(state: GraphState) -> GraphState:
        logger.info("analysis %s ingest start", state["analysis_id"])
        payload = {
            "email": state["email"],
            "cvDocId": state["cv_doc_id"],
            "jobDescription": state.get("job_description", ""),
            "jobDescriptionUrl": state.get("job_description_url"),
        }
        await deps.storage.update_status(state["analysis_id"], AnalysisStatus.RUNNING, payload)
        state["project_suggestions"] = []
        state["mvp_projects"] = []
        logger.info("analysis %s ingest complete", state["analysis_id"])
        return state

    return ingest
