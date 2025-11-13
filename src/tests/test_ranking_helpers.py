"""Focused tests for services.ranking helper methods to prevent regressions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.ranking import (
    DURATION_SPAN_SECONDS,
    HALF_LIFE_AFTER_3Y_DAYS,
    IDEAL_DURATION_SECONDS,
    MIN_DURATION_SECONDS,
    RankingService,
    THREE_YEARS_DAYS,
)


def test_parse_duration_seconds_handles_complete_iso_strings():
    service = RankingService()
    assert service._parse_duration_seconds("P1DT2H3M4S") == 86400 + 7200 + 180 + 4
    assert service._parse_duration_seconds("PT45M30S") == 45 * 60 + 30
    assert service._parse_duration_seconds("invalid") == 0


def test_duration_boost_rejects_short_videos_and_rewards_ideal_length():
    service = RankingService()
    assert service._duration_boost(MIN_DURATION_SECONDS - 60) == 0.0
    assert service._duration_boost(IDEAL_DURATION_SECONDS) == pytest.approx(1.10, rel=1e-3)
    # Slight deviation should decay linearly within the configured span.
    near_ideal = IDEAL_DURATION_SECONDS + DURATION_SPAN_SECONDS / 2
    assert service._duration_boost(int(near_ideal)) < 1.10


def test_time_decay_applies_half_life_after_three_years(monkeypatch):
    service = RankingService()
    anchor = datetime(2024, 1, 1, tzinfo=timezone.utc)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return anchor

    monkeypatch.setattr("services.ranking.datetime", FrozenDatetime)
    published = anchor - timedelta(days=THREE_YEARS_DAYS + HALF_LIFE_AFTER_3Y_DAYS)
    multiplier = service._time_decay(published.isoformat())
    assert multiplier == pytest.approx(0.5, rel=1e-2)
    assert service._time_decay("not-a-date") == 1.0


def test_semantic_boost_rewards_keywords_and_penalizes_vs_language():
    service = RankingService()
    boosted = service._semantic_boost(
        "Ultimate tutorial for beginners",
        "Hands on project from scratch",
        skill_name="tutorial",
    )
    penalized = service._semantic_boost(
        "Framework vs library comparison",
        "",
        skill_name=None,
    )
    assert boosted > 1.0
    assert penalized < 1.0


def test_sanitize_boosts_and_channel_defaults_work_together():
    service = RankingService()
    sanitized = service._sanitize_boosts({" freeCodeCamp.org ": "1.5", "": 0})
    assert sanitized == {"freecodecamp.org": 1.5}
    assert service._channel_boost("freeCodeCamp.org", None) > 1.0
