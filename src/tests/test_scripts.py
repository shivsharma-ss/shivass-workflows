"""Smoke tests for administrative scripts."""

from __future__ import annotations

import asyncio

import aiosqlite
import pytest

from scripts.clear_tokens import clear_tokens


class DummyRedis:
    """Minimal async Redis stub that captures flush calls."""

    def __init__(self) -> None:
        self.flushed = False

    async def flushall(self) -> None:
        await asyncio.sleep(0)  # exercise awaitable path
        self.flushed = True


@pytest.mark.asyncio
async def test_clear_tokens_clears_redis_and_sqlite(tmp_path, monkeypatch, capsys):
    """clear_tokens should wipe both Redis and the oauth_tokens table when present."""

    db_path = tmp_path / "orchestrator.db"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE oauth_tokens (
                provider TEXT NOT NULL,
                account TEXT NOT NULL,
                credentials TEXT NOT NULL
            )
            """
        )
        await db.execute(
            "INSERT INTO oauth_tokens (provider, account, credentials) VALUES (?, ?, ?)",
            ("google", "user@example.com", "{}"),
        )
        await db.commit()

    dummy = DummyRedis()
    monkeypatch.setattr("scripts.clear_tokens.aioredis.from_url", lambda url: dummy)

    await clear_tokens(redis_url="redis://localhost:6379/0", sqlite_path=db_path)

    assert dummy.flushed is True
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM oauth_tokens") as cursor:
            remaining, = await cursor.fetchone()
            assert remaining == 0

    out = capsys.readouterr().out
    assert "Cleared Redis cache" in out
    assert "Cleared SQLite oauth_tokens table" in out


@pytest.mark.asyncio
async def test_clear_tokens_handles_missing_resources(tmp_path, monkeypatch, capsys):
    """Failures in Redis or missing SQLite files should be reported instead of crashing."""

    class ExplodingRedis:
        async def flushall(self) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr("scripts.clear_tokens.aioredis.from_url", lambda url: ExplodingRedis())

    await clear_tokens(redis_url="redis://localhost:6379/0", sqlite_path=tmp_path / "missing.db")

    out = capsys.readouterr().out
    assert "Failed to clear Redis" in out
    assert "SQLite database not found" in out
