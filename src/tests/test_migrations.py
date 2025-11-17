"""Unit tests for migration helpers."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, text

from services.migrations import _load_schema_module, run_migrations


def test_load_schema_module_loads_migration_file():
    """_load_schema_module should successfully load the migration module."""
    module = _load_schema_module()
    assert hasattr(module, "apply_schema")
    assert hasattr(module, "upgrade")
    assert module.revision == "20240712_01_normalized_schema"


def test_load_schema_module_raises_if_file_missing(monkeypatch):
    """_load_schema_module should raise RuntimeError if migration file is missing."""
    fake_path = Path("/nonexistent/path/to/migration.py")
    monkeypatch.setattr("services.migrations._VERSION_FILE", fake_path)

    with pytest.raises(RuntimeError, match="Migration file .* is missing"):
        _load_schema_module()


def test_run_migrations_creates_tables_via_fallback(tmp_path, monkeypatch):
    """run_migrations should apply schema via fallback when Alembic is unavailable."""
    # Mock Alembic as unavailable
    monkeypatch.setattr("services.migrations.command", None)
    monkeypatch.setattr("services.migrations.Config", None)

    db_path = tmp_path / "test.db"
    run_migrations(db_path)

    # Verify tables were created
    engine = create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()

    assert "analyses" in tables
    assert "analysis_status_log" in tables
    assert "artifacts" in tables
    assert "node_events" in tables
    assert "youtube_queries" in tables
    assert "youtube_videos" in tables
    assert "oauth_accounts" in tables
    assert "oauth_tokens" in tables
    assert "cache_entries" in tables


def test_run_migrations_uses_alembic_when_available(tmp_path, monkeypatch):
    """run_migrations should use Alembic command when available."""
    mock_config = MagicMock()
    mock_command = MagicMock()

    monkeypatch.setattr("services.migrations.Config", lambda path: mock_config)
    monkeypatch.setattr("services.migrations.command", mock_command)

    db_path = tmp_path / "test.db"
    run_migrations(db_path)

    mock_config.set_main_option.assert_any_call("sqlalchemy.url", f"sqlite:///{db_path}")
    mock_config.set_main_option.assert_any_call("db_path", str(db_path))
    mock_command.upgrade.assert_called_once_with(mock_config, "head")


def test_run_migrations_creates_views(tmp_path, monkeypatch):
    """run_migrations should create views for analysis_latest and oauth_active."""
    monkeypatch.setattr("services.migrations.command", None)
    monkeypatch.setattr("services.migrations.Config", None)

    db_path = tmp_path / "test.db"
    run_migrations(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)

    # Views aren't directly listed by inspector, so query sqlite_master
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='view'")
        ).fetchall()
        view_names = {row[0] for row in result}

    assert "analysis_latest" in view_names
    assert "oauth_active" in view_names
    assert "node_latest_output" in view_names


def test_run_migrations_creates_indexes(tmp_path, monkeypatch):
    """run_migrations should create indexes on frequently queried columns."""
    monkeypatch.setattr("services.migrations.command", None)
    monkeypatch.setattr("services.migrations.Config", None)

    db_path = tmp_path / "test.db"
    run_migrations(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index'")
        ).fetchall()
        index_names = {row[0] for row in result}

    assert "ix_analysis_status_log_analysis_id" in index_names
    assert "ix_artifacts_analysis" in index_names
    assert "ix_node_events_analysis_node" in index_names
    assert "ix_cache_entries_namespace" in index_names


def test_run_migrations_creates_trigger(tmp_path, monkeypatch):
    """run_migrations should create trigger to update analyses.updated_at."""
    monkeypatch.setattr("services.migrations.command", None)
    monkeypatch.setattr("services.migrations.Config", None)

    db_path = tmp_path / "test.db"
    run_migrations(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='trigger'")
        ).fetchall()
        trigger_names = {row[0] for row in result}

    assert "trg_analysis_status_updated" in trigger_names


def test_run_migrations_idempotent(tmp_path, monkeypatch):
    """run_migrations should be safe to run multiple times."""
    monkeypatch.setattr("services.migrations.command", None)
    monkeypatch.setattr("services.migrations.Config", None)

    db_path = tmp_path / "test.db"

    # Run migrations twice
    run_migrations(db_path)
    run_migrations(db_path)

    # Verify database is still intact
    engine = create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()

    assert len(tables) >= 9  # All expected tables present


def test_migration_schema_enables_foreign_keys(tmp_path, monkeypatch):
    """Migration should enable foreign key constraints."""
    monkeypatch.setattr("services.migrations.command", None)
    monkeypatch.setattr("services.migrations.Config", None)

    db_path = tmp_path / "test.db"
    run_migrations(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        # Insert into analyses
        conn.execute(
            text(
                "INSERT INTO analyses (id, email, cv_doc_id) VALUES ('a1', 'test@example.com', 'doc1')"
            )
        )
        conn.commit()

        # Foreign key constraint should prevent inserting status with invalid analysis_id
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO analysis_status_log (analysis_id, status) VALUES ('nonexistent', 'pending')"
                )
            )
            conn.commit()


def test_migration_cascades_on_delete(tmp_path, monkeypatch):
    """Migration should set up CASCADE delete for child records."""
    monkeypatch.setattr("services.migrations.command", None)
    monkeypatch.setattr("services.migrations.Config", None)

    db_path = tmp_path / "test.db"
    run_migrations(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        # Enable foreign keys for this connection
        conn.execute(text("PRAGMA foreign_keys = ON"))

        # Insert parent analysis
        conn.execute(
            text(
                "INSERT INTO analyses (id, email, cv_doc_id) VALUES ('a1', 'test@example.com', 'doc1')"
            )
        )
        # Insert child status log
        conn.execute(
            text(
                "INSERT INTO analysis_status_log (analysis_id, status) VALUES ('a1', 'pending')"
            )
        )
        conn.commit()

        # Verify child exists
        result = conn.execute(
            text("SELECT COUNT(*) FROM analysis_status_log WHERE analysis_id = 'a1'")
        ).scalar()
        assert result == 1

        # Delete parent
        conn.execute(text("DELETE FROM analyses WHERE id = 'a1'"))
        conn.commit()

        # Child should be deleted via CASCADE
        result = conn.execute(
            text("SELECT COUNT(*) FROM analysis_status_log WHERE analysis_id = 'a1'")
        ).scalar()
        assert result == 0