"""Shared defaults for preferred YouTube channels."""
from __future__ import annotations

from copy import deepcopy

DEFAULT_CHANNEL_SUGGESTIONS = [
    {"name": "freeCodeCamp.org", "boost": 1.10},
    {"name": "Tech With Tim", "boost": 1.10},
    {"name": "TechWithTim", "boost": 1.10},
    {"name": "IBM Technology", "boost": 1.10},
]


def default_channel_boost_map() -> dict[str, float]:
    """Return a lowercase map used by RankingService when no user overrides exist."""

    result: dict[str, float] = {}
    for item in DEFAULT_CHANNEL_SUGGESTIONS:
        name = item.get("name", "").strip().lower()
        boost = float(item.get("boost", 1.0) or 1.0)
        if not name or boost <= 0:
            continue
        result[name] = boost
    return result


def clone_default_channel_list() -> list[dict[str, float]]:
    """Return a deep copy so callers can mutate without touching module state."""

    return deepcopy(DEFAULT_CHANNEL_SUGGESTIONS)
