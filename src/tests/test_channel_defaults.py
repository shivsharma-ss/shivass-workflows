"""Validation for shared channel defaults to keep UI/API parity."""

from __future__ import annotations

from services.channel_defaults import (
    DEFAULT_CHANNEL_SUGGESTIONS,
    clone_default_channel_list,
    default_channel_boost_map,
)


def test_default_channel_boost_map_lowercases_and_filters_invalid_entries():
    mapping = default_channel_boost_map()
    assert mapping  # ensure we have at least one suggestion configured
    for name, boost in mapping.items():
        assert name == name.lower()
        assert boost > 0
    source_names = {item["name"].strip().lower() for item in DEFAULT_CHANNEL_SUGGESTIONS}
    assert set(mapping.keys()) == source_names


def test_clone_default_channel_list_returns_deep_copy():
    clone = clone_default_channel_list()
    assert clone == DEFAULT_CHANNEL_SUGGESTIONS
    clone[0]["name"] = "Mutated"
    assert DEFAULT_CHANNEL_SUGGESTIONS[0]["name"] != "Mutated"
