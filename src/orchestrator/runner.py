"""High-level workflow runner built on top of LangGraph."""
from __future__ import annotations

from typing import Any, Tuple
from uuid import uuid4

from app.schemas import AnalysisRequest, AnalysisStatus, CvAnalysisLLMResponse, CvScoreLLMResponse, ImprovementPlan, ProjectSuggestion
from orchestrator.exceptions import ApprovalPendingError
from orchestrator.state import GraphState, NodeDeps


class OrchestratorRunner:
    """Coordinates LangGraph invocation, persistence, and resume logic."""

    def __init__(self, graph, deps: NodeDeps):
        self._graph = graph
        self._deps = deps

    async def kickoff(self, payload: AnalysisRequest) -> Tuple[str, AnalysisStatus]:
        """Start a new analysis and return its ID + status."""

        analysis_id = uuid4().hex
        state: GraphState = {
            "analysis_id": analysis_id,
            "email": payload.email,
            "cv_doc_id": payload.cvDocId,
            "job_description": payload.jobDescription or "",
            "job_description_url": str(payload.jobDescriptionUrl) if payload.jobDescriptionUrl else None,
        }
        await self._deps.storage.create_analysis(
            analysis_id=analysis_id,
            email=payload.email,
            cv_doc_id=payload.cvDocId,
            payload=self._state_to_payload(state),
        )
        state, status = await self._run(state)
        return analysis_id, status

    async def resume(self, analysis_id: str) -> AnalysisStatus:
        """Resume a paused workflow once reviewer approves edits."""

        record = await self._deps.storage.get_analysis(analysis_id)
        if not record:
            raise ValueError("Unknown analysis ID")
        state = self._payload_to_state(record.payload)
        state["analysis_id"] = analysis_id
        state["email"] = record.email
        state["cv_doc_id"] = record.cv_doc_id
        state["approval_granted"] = True
        state["awaiting_approval"] = False
        _, status = await self._run(state)
        return status

    async def _run(self, state: GraphState) -> tuple[GraphState, AnalysisStatus]:
        try:
            result = await self._graph.ainvoke(state)
            await self._deps.storage.update_status(
                state["analysis_id"],
                AnalysisStatus.COMPLETED,
                self._state_to_payload(result),
            )
            return result, AnalysisStatus.COMPLETED
        except ApprovalPendingError as exc:
            awaiting_state = exc.state or state
            await self._deps.storage.update_status(
                state["analysis_id"],
                AnalysisStatus.AWAITING_APPROVAL,
                self._state_to_payload(awaiting_state),
            )
            return awaiting_state, AnalysisStatus.AWAITING_APPROVAL

    def _state_to_payload(self, state: GraphState) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "analysis_id": state.get("analysis_id"),
            "email": state.get("email"),
            "cv_doc_id": state.get("cv_doc_id"),
            "job_description": state.get("job_description"),
            "job_description_url": state.get("job_description_url"),
            "cv_text": state.get("cv_text"),
            "jd_text": state.get("jd_text"),
            "awaiting_approval": state.get("awaiting_approval", False),
            "approval_token": state.get("approval_token"),
            "approval_granted": state.get("approval_granted", False),
        }
        if state.get("cv_analysis"):
            payload["cv_analysis"] = state["cv_analysis"].model_dump()
        if state.get("score"):
            payload["score"] = state["score"].model_dump()
        if state.get("improvements"):
            payload["improvements"] = state["improvements"].model_dump()
        if state.get("project_suggestions"):
            payload["project_suggestions"] = [s.model_dump() for s in state["project_suggestions"]]
        return payload

    def _payload_to_state(self, payload: dict[str, Any]) -> GraphState:
        state: GraphState = {
            "job_description": payload.get("job_description", ""),
            "job_description_url": payload.get("job_description_url"),
            "cv_text": payload.get("cv_text", ""),
            "jd_text": payload.get("jd_text", ""),
            "awaiting_approval": payload.get("awaiting_approval", False),
            "approval_token": payload.get("approval_token"),
            "approval_granted": payload.get("approval_granted", False),
        }
        if payload.get("cv_analysis"):
            state["cv_analysis"] = CvAnalysisLLMResponse.model_validate(payload["cv_analysis"])
        if payload.get("score"):
            state["score"] = CvScoreLLMResponse.model_validate(payload["score"])
        if payload.get("improvements"):
            state["improvements"] = ImprovementPlan.model_validate(payload["improvements"])
        if payload.get("project_suggestions"):
            suggestions = [ProjectSuggestion.model_validate(item) for item in payload["project_suggestions"]]
            state["project_suggestions"] = suggestions
        return state
