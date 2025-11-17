"""Utility helpers for orchestrator nodes."""
from __future__ import annotations

import functools
import json
from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from orchestrator.state import GraphState, NodeDeps


def _snapshot_state(state: GraphState) -> dict[str, Any]:
    snapshot = deepcopy({key: state.get(key) for key in state.keys()})

    def _default(obj: Any) -> Any:
        if hasattr(obj, "model_dump"):
            try:
                return obj.model_dump(mode="json")
            except TypeError:
                return obj.model_dump()
        if isinstance(obj, set):
            return list(obj)
        return obj

    try:
        json.dumps(snapshot, default=_default)
    except TypeError:
        snapshot = json.loads(json.dumps(snapshot, default=_default))
    return snapshot


def instrument_node(node_name: str, deps: NodeDeps, func: Callable[[GraphState], Awaitable[GraphState]]):
    """Wrap a node callable with storage-backed telemetry logging."""

    @functools.wraps(func)
    async def wrapper(state: GraphState) -> GraphState:
        started_at = datetime.now(timezone.utc).isoformat()
        before = _snapshot_state(state)
        analysis_id = state.get("analysis_id", "")
        try:
            result = await func(state)
            record_id = result.get("analysis_id") or analysis_id
            if record_id:
                await deps.storage.record_node_event(
                    analysis_id=record_id,
                    node_name=node_name,
                    state_before=before,
                    output=_snapshot_state(result),
                    started_at=started_at,
                    error=None,
                )
            return result
        except Exception as exc:
            if analysis_id:
                await deps.storage.record_node_event(
                    analysis_id=analysis_id,
                    node_name=node_name,
                    state_before=before,
                    output={},
                    started_at=started_at,
                    error=str(exc),
                )
            raise

    return wrapper
