"""Aggregates fan-in nodes (noop placeholder)."""
from __future__ import annotations

import logging

from orchestrator.state import GraphState, NodeDeps
from orchestrator.utils import instrument_node

logger = logging.getLogger(__name__)


def build_node(deps: NodeDeps):
    async def collect(state: GraphState) -> GraphState:
        state.setdefault("project_suggestions", [])
        logger.debug(
            "analysis %s collect barrier reached (%d suggestions)",
            state["analysis_id"],
            len(state["project_suggestions"]),
        )
        return state

    return instrument_node("collect", deps, collect)
