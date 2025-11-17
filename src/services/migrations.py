"""Alembic migration helpers for runtime initialization."""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from types import ModuleType

from sqlalchemy import create_engine

try:  # pragma: no cover - optional dependency
    from alembic import command
    from alembic.config import Config
except ImportError:  # pragma: no cover - fallback path exercised in tests
    command = None
    Config = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_VERSION_FILE = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "20240712_01_normalized_schema.py"


def _load_schema_module() -> ModuleType:
    if not _VERSION_FILE.exists():  # pragma: no cover - developer misconfiguration
        raise RuntimeError(f"Migration file {_VERSION_FILE} is missing")
    spec = importlib.util.spec_from_file_location("local_alembic_version", _VERSION_FILE)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"Unable to load migration spec from {_VERSION_FILE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_migrations(database_path: Path) -> None:
    """Run Alembic migrations against the provided SQLite database."""

    if command is None or Config is None:
        schema_module = _load_schema_module()
        engine = create_engine(f"sqlite:///{database_path}")
        with engine.begin() as connection:
            schema_module.apply_schema(connection)
        logger.info("Database migrations applied via fallback for %s", database_path)
        return

    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    config.set_main_option("db_path", str(database_path))
    command.upgrade(config, "head")
    logger.info("Database migrations complete for %s", database_path)
