"""Unit tests for orchestrator utility functions."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from orchestrator.state import GraphState, NodeDeps
from orchestrator.utils import _snapshot_state, instrument_node


class FakeStorage:
    """Mock storage service for testing node instrumentation."""

    def __init__(self):
        self.events: list[dict[str, Any]] = []

    async def record_node_event(
        self,
        analysis_id: str,
        node_name: str,
        state_before: dict[str, Any] | None = None,
        output: dict[str, Any] | None = None,
        *,
        started_at: str | None = None,
        error: str | None = None,
    ) -> None:
        self.events.append(
            {
                "analysis_id": analysis_id,
                "node_name": node_name,
                "state_before": state_before,
                "output": output,
                "started_at": started_at,
                "error": error,
            }
        )


def test_snapshot_state_handles_simple_dict():
    """Snapshot should deep-copy simple dictionary state."""
    state: GraphState = {"key": "value", "number": 42}
    snapshot = _snapshot_state(state)
    assert snapshot == {"key": "value", "number": 42}
    state["key"] = "modified"
    assert snapshot["key"] == "value"


def test_snapshot_state_handles_pydantic_models():
    """Snapshot should serialize Pydantic models using model_dump."""
    from app.schemas import TutorialSuggestion

    tutorial = TutorialSuggestion(
        tutorialTitle="Test Tutorial",
        tutorialUrl="https://example.com",
        personalizationTip="Try this",
    )
    state: GraphState = {"tutorial": tutorial}
    snapshot = _snapshot_state(state)
    assert isinstance(snapshot["tutorial"], dict)
    assert snapshot["tutorial"]["tutorialTitle"] == "Test Tutorial"


def test_snapshot_state_handles_sets():
    """Snapshot should convert sets to lists for JSON compatibility."""
    state: GraphState = {"skills": {"Python", "JavaScript", "Go"}}
    snapshot = _snapshot_state(state)
    assert isinstance(snapshot["skills"], list)
    assert set(snapshot["skills"]) == {"Python", "JavaScript", "Go"}


def test_snapshot_state_handles_nested_structures():
    """Snapshot should handle deeply nested structures."""
    state: GraphState = {
        "nested": {
            "level1": {"level2": {"value": "deep"}},
            "list": [1, 2, 3],
        }
    }
    snapshot = _snapshot_state(state)
    assert snapshot["nested"]["level1"]["level2"]["value"] == "deep"
    state["nested"]["level1"]["level2"]["value"] = "modified"
    assert snapshot["nested"]["level1"]["level2"]["value"] == "deep"


def test_snapshot_state_handles_non_serializable_objects():
    """Snapshot should gracefully handle objects that require type conversion."""

    class CustomObject:
        def __str__(self):
            return "custom"

    state: GraphState = {"custom": CustomObject()}
    snapshot = _snapshot_state(state)
    assert snapshot is not None


@pytest.mark.asyncio
async def test_instrument_node_records_successful_execution():
    """Instrumented node should log state before/after on success."""
    storage = FakeStorage()
    deps = NodeDeps(
        settings=None,
        storage=storage,
        drive=None,
        docs=None,
        gmail=None,
        llm=None,
        ranking=None,
        youtube=None,
        gemini=None,
    )

    async def sample_node(state: GraphState) -> GraphState:
        return {**state, "processed": True}

    instrumented = instrument_node("test_node", deps, sample_node)
    initial_state: GraphState = {"analysis_id": "test-123", "input": "data"}
    result = await instrumented(initial_state)

    assert result["processed"] is True
    assert len(storage.events) == 1
    event = storage.events[0]
    assert event["analysis_id"] == "test-123"
    assert event["node_name"] == "test_node"
    assert event["state_before"]["input"] == "data"
    assert event["output"]["processed"] is True
    assert event["error"] is None
    assert event["started_at"] is not None


@pytest.mark.asyncio
async def test_instrument_node_records_failures():
    """Instrumented node should log errors when execution fails."""
    storage = FakeStorage()
    deps = NodeDeps(
        settings=None,
        storage=storage,
        drive=None,
        docs=None,
        gmail=None,
        llm=None,
        ranking=None,
        youtube=None,
        gemini=None,
    )

    async def failing_node(state: GraphState) -> GraphState:
        raise ValueError("Something went wrong")

    instrumented = instrument_node("failing_node", deps, failing_node)
    initial_state: GraphState = {"analysis_id": "test-456"}

    with pytest.raises(ValueError, match="Something went wrong"):
        await instrumented(initial_state)

    assert len(storage.events) == 1
    event = storage.events[0]
    assert event["analysis_id"] == "test-456"
    assert event["node_name"] == "failing_node"
    assert event["error"] == "Something went wrong"
    assert event["output"] == {}


@pytest.mark.asyncio
async def test_instrument_node_handles_missing_analysis_id():
    """Instrumented node should skip logging when analysis_id is missing."""
    storage = FakeStorage()
    deps = NodeDeps(
        settings=None,
        storage=storage,
        drive=None,
        docs=None,
        gmail=None,
        llm=None,
        ranking=None,
        youtube=None,
        gemini=None,
    )

    async def node_without_id(state: GraphState) -> GraphState:
        return {**state, "result": "done"}

    instrumented = instrument_node("no_id_node", deps, node_without_id)
    result = await instrumented({})

    assert result["result"] == "done"
    assert len(storage.events) == 0


@pytest.mark.asyncio
async def test_instrument_node_captures_analysis_id_from_result():
    """If initial state lacks analysis_id but result has it, use result's ID."""
    storage = FakeStorage()
    deps = NodeDeps(
        settings=None,
        storage=storage,
        drive=None,
        docs=None,
        gmail=None,
        llm=None,
        ranking=None,
        youtube=None,
        gemini=None,
    )

    async def node_adds_id(state: GraphState) -> GraphState:
        return {**state, "analysis_id": "new-789"}

    instrumented = instrument_node("adds_id_node", deps, node_adds_id)
    result = await instrumented({"data": "initial"})

    assert result["analysis_id"] == "new-789"
    assert len(storage.events) == 1
    assert storage.events[0]["analysis_id"] == "new-789"


@pytest.mark.asyncio
async def test_instrument_node_preserves_function_metadata():
    """Instrumented function should preserve original function's metadata."""

    async def original_function(state: GraphState) -> GraphState:
        """Original docstring."""
        return state

    storage = FakeStorage()
    deps = NodeDeps(
        settings=None,
        storage=storage,
        drive=None,
        docs=None,
        gmail=None,
        llm=None,
        ranking=None,
        youtube=None,
        gemini=None,
    )
    instrumented = instrument_node("test", deps, original_function)

    assert instrumented.__name__ == "original_function"
    assert instrumented.__doc__ == "Original docstring."


@pytest.mark.asyncio
async def test_instrument_node_with_complex_state():
    """Instrumented node should handle complex state with Pydantic models."""
    from app.schemas import TutorialSuggestion

    storage = FakeStorage()
    deps = NodeDeps(
        settings=None,
        storage=storage,
        drive=None,
        docs=None,
        gmail=None,
        llm=None,
        ranking=None,
        youtube=None,
        gemini=None,
    )

    async def complex_node(state: GraphState) -> GraphState:
        tutorial = TutorialSuggestion(
            tutorialTitle="Advanced Testing",
            tutorialUrl="https://example.com/test",
            personalizationTip="Focus on edge cases",
        )
        return {**state, "tutorial": tutorial}

    instrumented = instrument_node("complex", deps, complex_node)
    result = await instrumented({"analysis_id": "complex-1"})

    assert "tutorial" in result
    assert len(storage.events) == 1
    event = storage.events[0]
    assert isinstance(event["output"]["tutorial"], dict)
    assert event["output"]["tutorial"]["tutorialTitle"] == "Advanced Testing"