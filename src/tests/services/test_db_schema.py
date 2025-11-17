"""Regression tests that guard sqlite schema drift."""

from __future__ import annotations

import sqlite3
import pytest

from services.storage import AnalysisStatus, StorageService


@pytest.mark.asyncio
async def test_migrations_create_expected_schema(tmp_path):
    db_path = tmp_path / "schema.db"
    storage = StorageService(f"sqlite+aiosqlite:///{db_path}")
    await storage.initialize()

    expected_tables = {
        "analyses": {"id", "email", "cv_doc_id", "approval_token", "created_at", "updated_at"},
        "analysis_inputs": {"analysis_id", "payload", "created_at"},
        "analysis_status_log": {"analysis_id", "status", "payload", "last_error", "recorded_at"},
        "artifacts": {"id", "analysis_id", "artifact_type", "version", "content", "created_at"},
        "node_events": {
            "id",
            "analysis_id",
            "node_name",
            "started_at",
            "completed_at",
            "state_before",
            "output",
            "error",
        },
        "youtube_queries": {"id", "analysis_id", "skill", "query", "created_at"},
        "youtube_videos": {
            "video_id",
            "title",
            "url",
            "channel_title",
            "duration",
            "view_count",
            "like_count",
            "fetched_at",
        },
        "youtube_query_results": {"query_id", "video_id", "rank"},
        "video_analyses": {
            "video_id",
            "model",
            "summary",
            "key_points",
            "difficulty_level",
            "prerequisites",
            "takeaways",
            "skills",
            "tech_stack",
            "cached_at",
        },
        "oauth_accounts": {"provider", "account", "created_at"},
        "oauth_tokens": {
            "provider",
            "account",
            "version",
            "encrypted_credentials",
            "issued_at",
            "expires_at",
        },
        "cache_entries": {
            "cache_key",
            "namespace",
            "value",
            "created_at",
            "expires_at",
            "last_accessed",
        },
    }

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        for table, expected_columns in expected_tables.items():
            cursor.execute(f"PRAGMA table_info({table})")
            columns = {row[1] for row in cursor.fetchall()}
            assert expected_columns <= columns, f"{table} is missing columns {expected_columns - columns}"


@pytest.mark.asyncio
async def test_storage_initialize_is_idempotent(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'storage.db'}"
    storage = StorageService(db_url)
    await storage.initialize()
    await storage.create_analysis("run-1", "user@example.com", "doc", {"foo": "bar"})
    await storage.initialize()
    record = await storage.get_analysis("run-1")
    assert record is not None
    assert record.status == AnalysisStatus.PENDING
