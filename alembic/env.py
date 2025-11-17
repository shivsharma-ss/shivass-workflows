"""Alembic environment configuration."""
from __future__ import annotations

import logging
from logging.config import fileConfig
from pathlib import Path
from typing import Any

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection

# Interpret the config file for Python logging.
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
logger = logging.getLogger("alembic.env")

# No SQLAlchemy models are bound; migrations use imperative SQL.
target_metadata = None


def _get_url() -> str:
    override = config.get_main_option("sqlalchemy.url")
    if override and override != "sqlite:///./data/orchestrator.db":
        return override
    db_path = config.get_main_option("db_path")
    if db_path:
        return f"sqlite:///{Path(db_path).resolve()}"
    return override


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""

    url = _get_url()
    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    connection: Connection | None = context.config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return

    configuration: dict[str, Any] = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
