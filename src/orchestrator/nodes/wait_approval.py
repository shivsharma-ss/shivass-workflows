"""Marks state as blocked for approval."""
from __future__ import annotations

import logging

from orchestrator.state import GraphState, NodeDeps

logger = logging.getLogger(__name__)


def build_node(deps: NodeDeps):
    async def wait(state: GraphState) -> GraphState:
        state["awaiting_approval"] = True
        logger.info("analysis %s paused awaiting approval", state["analysis_id"])
        return state

    return wait
