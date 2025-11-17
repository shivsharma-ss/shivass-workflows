"""Applies improvements to Google Docs."""
from __future__ import annotations

import asyncio
import logging

from app.schemas import ImprovementPlan
from orchestrator.exceptions import ApprovalPendingError
from orchestrator.state import GraphState, NodeDeps
from orchestrator.utils import instrument_node

logger = logging.getLogger(__name__)


def build_node(deps: NodeDeps):
    async def docs_apply(state: GraphState) -> GraphState:
        if not state.get("approval_granted"):
            logger.warning("analysis %s attempted doc apply without approval", state["analysis_id"])
            raise ApprovalPendingError(state["analysis_id"], state)
        improvements = state.get("improvements")
        if not improvements:
            logger.info("analysis %s no improvements to apply", state["analysis_id"])
            return state
        text = _format_improvements(improvements)
        logger.info("analysis %s applying improvements to doc %s", state["analysis_id"], state["cv_doc_id"])
        await asyncio.to_thread(deps.docs.prepend_text, state["cv_doc_id"], text)
        state["cv_text"] = f"{text}\\n{state['cv_text']}"
        await deps.storage.save_artifact(state["analysis_id"], "applied_improvements", text)
        return state

    return instrument_node("docs_apply", deps, docs_apply)


def _format_improvements(improvements: ImprovementPlan) -> str:
    parts: list[str] = ["CV Alignment Suggestions\n-----------------------\n"]
    if improvements.reformulations:
        parts.append("Reformulations:\n")
        for item in improvements.reformulations:
            parts.append(f"- {item.original} -> {item.improved} ({item.reason})\n")
    if improvements.removals:
        parts.append("Removals:\n")
        for item in improvements.removals:
            parts.append(f"- {item.text} ({item.reason})\n")
    if improvements.additions:
        parts.append("Additions:\n")
        for item in improvements.additions:
            parts.append(f"- {item.section}: {item.content} ({item.reason})\n")
    return "".join(parts)
