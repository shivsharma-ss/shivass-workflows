"""Script to clear all OAuth tokens from both Redis and SQLite."""
from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite
from redis import asyncio as aioredis


async def clear_tokens(
    redis_url: str | None = "redis://localhost:6379/0",
    sqlite_path: str | Path = "./data/orchestrator.db",
) -> None:
    """Remove cached OAuth credentials from Redis and SQLite.

    Parameters mirror the default local stack, but tests may inject temporary
    paths/URLs so the script can run against disposable resources.
    """

    if redis_url:
        try:
            redis = aioredis.from_url(redis_url)
            await redis.flushall()
            print(f"✓ Cleared Redis cache ({redis_url})")
        except Exception as exc:  # pragma: no cover - printed for visibility
            print(f"! Failed to clear Redis: {exc}")
    else:
        print("! Redis URL not provided; skipping Redis cache")

    db_path = Path(sqlite_path)
    if db_path.exists():
        try:
            async with aiosqlite.connect(db_path) as db:
                await db.execute("DELETE FROM oauth_tokens")
                await db.commit()
                print(f"✓ Cleared SQLite oauth_tokens table ({db_path})")
        except Exception as exc:  # pragma: no cover - printed for visibility
            print(f"! Failed to clear SQLite tokens: {exc}")
    else:
        print("! SQLite database not found (this is normal if you haven't authorized yet)")


if __name__ == "__main__":
    asyncio.run(clear_tokens())
