"""Script to clear all OAuth tokens from both Redis and SQLite."""
import asyncio
from pathlib import Path

import aiosqlite
from redis import asyncio as aioredis


async def clear_tokens():
    # Clear Redis
    try:
        redis = aioredis.from_url('redis://localhost:6379/0')
        await redis.flushall()
        print("✓ Cleared Redis cache")
    except Exception as e:
        print(f"! Failed to clear Redis: {e}")

    # Clear SQLite oauth_tokens table
    db_path = Path('./data/orchestrator.db')
    if db_path.exists():
        try:
            async with aiosqlite.connect(db_path) as db:
                await db.execute("DELETE FROM oauth_tokens")
                await db.commit()
                print("✓ Cleared SQLite oauth_tokens table")
        except Exception as e:
            print(f"! Failed to clear SQLite tokens: {e}")
    else:
        print("! SQLite database not found (this is normal if you haven't authorized yet)")

if __name__ == "__main__":
    asyncio.run(clear_tokens())