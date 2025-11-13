"""Regression tests that guard sqlite schema drift."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services.storage import AnalysisStatus, StorageService


def test_bundled_database_matches_expected_schema():
    db_path = Path("data/orchestrator.db")
    assert db_path.exists(), "Bundled orchestrator.db is missing"

    expected_tables = {
        "analysis_runs": {
            "analysis_id",
            "email",
            "cv_doc_id",
            "status",
            "payload",
            "approval_token",
            "last_error",
            "created_at",
            "updated_at",
        },
        "analysis_artifacts": {"analysis_id", "artifact_type", "content", "created_at"},
        "oauth_tokens": {"provider", "account", "credentials", "created_at", "updated_at"},
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
