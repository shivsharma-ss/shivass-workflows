"""Custom exceptions for orchestration control flow."""
from __future__ import annotations


from typing import Optional

from orchestrator.state import GraphState


class ApprovalPendingError(RuntimeError):
    """Raised when the workflow must pause for reviewer approval."""

    def __init__(self, analysis_id: str, state: Optional[GraphState] = None):
        super().__init__(f"Analysis {analysis_id} is awaiting approval")
        self.analysis_id = analysis_id
        self.state = state
