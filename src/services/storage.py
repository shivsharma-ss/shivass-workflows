"""Persistence layer powered by SQLite via aiosqlite."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import aiosqlite

from app.schemas import AnalysisStatus


def _json_default(value: Any):
    """Best-effort conversion for objects json can't serialize."""

    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(mode="json")
        except TypeError:
            return value.model_dump()
    if isinstance(value, set):
        return list(value)
    return str(value)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, default=_json_default)


@dataclass
class AnalysisRecord:
    """Represents one analysis row stored in SQLite."""

    analysis_id: str
    email: str
    cv_doc_id: str
    status: AnalysisStatus
    payload: dict[str, Any]
    approval_token: Optional[str]
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime


class StorageService:
    """Simple async storage abstraction over SQLite."""

    def __init__(self, db_url: str):
        if not db_url.startswith("sqlite"):
            raise ValueError("Only SQLite URLs are supported in this reference implementation")
        path = db_url.split("///")[-1]
        self._db_path = Path(path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Create tables idempotently."""

        async with self._init_lock:
            if self._initialized:
                return
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS analysis_runs (
                        analysis_id TEXT PRIMARY KEY,
                        email TEXT NOT NULL,
                        cv_doc_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        approval_token TEXT,
                        last_error TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS analysis_artifacts (
                        analysis_id TEXT NOT NULL,
                        artifact_type TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(analysis_id, artifact_type)
                    )
                    """
                )
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS youtube_cache (
                        query TEXT PRIMARY KEY,
                        videos TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS youtube_video_metadata (
                        video_url TEXT PRIMARY KEY,
                        summary TEXT,
                        skills TEXT,
                        tech_stack TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS oauth_tokens (
                        provider TEXT NOT NULL,
                        account TEXT NOT NULL,
                        credentials TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(provider, account)
                    )
                    """
                )
                await db.commit()
            self._initialized = True

    async def _execute(self, query: str, *params: Any) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(query, params)
            await db.commit()

    async def _fetchone(self, query: str, *params: Any) -> Optional[aiosqlite.Row]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                return await cursor.fetchone()

    async def create_analysis(self, analysis_id: str, email: str, cv_doc_id: str, payload: dict[str, Any]) -> None:
        """Insert a new analysis with initial payload."""

        now = datetime.now(timezone.utc).isoformat()
        await self._execute(
            """
            INSERT OR REPLACE INTO analysis_runs
            (analysis_id, email, cv_doc_id, status, payload, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            analysis_id,
            email,
            cv_doc_id,
            AnalysisStatus.PENDING.value,
            _json_dumps(payload),
            now,
            now,
        )

    async def update_status(
        self,
        analysis_id: str,
        status: AnalysisStatus,
        payload: Optional[dict[str, Any]] = None,
        last_error: Optional[str] = None,
    ) -> None:
        """Update lifecycle status and optionally overwrite payload and last error."""

        now = datetime.now(timezone.utc).isoformat()
        if payload is None:
            record = await self.get_analysis(analysis_id)
            payload_json = _json_dumps(record.payload if record else {})
        else:
            payload_json = _json_dumps(payload)
        await self._execute(
            """
            UPDATE analysis_runs
               SET status = ?,
                   payload = ?,
                   last_error = ?,
                   updated_at = ?
             WHERE analysis_id = ?
            """,
            status.value,
            payload_json,
            last_error,
            now,
            analysis_id,
        )

    async def save_payload(self, analysis_id: str, payload: dict[str, Any]) -> None:
        """Persist arbitrary payload JSON."""

        await self._execute(
            "UPDATE analysis_runs SET payload = ?, updated_at = ? WHERE analysis_id = ?",
            _json_dumps(payload),
            datetime.now(timezone.utc).isoformat(),
            analysis_id,
        )

    async def set_approval_token(self, analysis_id: str, token: str) -> None:
        """Store the approval token so future callbacks can be validated."""

        await self._execute(
            "UPDATE analysis_runs SET approval_token = ?, updated_at = ? WHERE analysis_id = ?",
            token,
            datetime.now(timezone.utc).isoformat(),
            analysis_id,
        )

    async def get_analysis(self, analysis_id: str) -> Optional[AnalysisRecord]:
        """Fetch a single analysis row."""

        row = await self._fetchone("SELECT * FROM analysis_runs WHERE analysis_id = ?", analysis_id)
        if not row:
            return None
        payload = json.loads(row["payload"]) if row["payload"] else {}
        return AnalysisRecord(
            analysis_id=row["analysis_id"],
            email=row["email"],
            cv_doc_id=row["cv_doc_id"],
            status=AnalysisStatus(row["status"]),
            payload=payload,
            approval_token=row["approval_token"],
            last_error=row["last_error"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    async def save_artifact(self, analysis_id: str, artifact_type: str, content: Any) -> None:
        """Persist intermediate artifact content keyed by analysis and type."""

        if isinstance(content, str):
            serialized = content
        else:
            serialized = _json_dumps(content)
        await self._execute(
            """
            INSERT INTO analysis_artifacts (analysis_id, artifact_type, content, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(analysis_id, artifact_type)
            DO UPDATE SET content=excluded.content, created_at=excluded.created_at
            """,
            analysis_id,
            artifact_type,
            serialized,
            datetime.now(timezone.utc).isoformat(),
        )

    async def get_artifact(self, analysis_id: str, artifact_type: str) -> Optional[str]:
        """Return the stored artifact payload, if any."""

        row = await self._fetchone(
            "SELECT content FROM analysis_artifacts WHERE analysis_id = ? AND artifact_type = ?",
            analysis_id,
            artifact_type,
        )
        return row["content"] if row else None

    async def save_youtube_cache(self, query: str, videos: list[dict[str, Any]]) -> None:
        """Persist rendered YouTube results so future runs can reuse them."""

        await self._execute(
            """
            INSERT INTO youtube_cache (query, videos, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(query)
            DO UPDATE SET videos=excluded.videos, created_at=excluded.created_at
            """,
            query,
            _json_dumps(videos),
            datetime.now(timezone.utc).isoformat(),
        )

    async def get_youtube_cache(self, query: str, max_age_seconds: int = 86400) -> Optional[list[dict[str, Any]]]:
        """Return cached YouTube entries if still fresh."""

        row = await self._fetchone("SELECT videos, created_at FROM youtube_cache WHERE query = ?", query)
        if not row:
            return None
        saved_at = datetime.fromisoformat(row["created_at"])
        if datetime.now(timezone.utc) - saved_at > timedelta(seconds=max_age_seconds):
            return None
        return json.loads(row["videos"])

    async def save_youtube_video_metadata(
        self,
        video_url: str,
        summary: Optional[str],
        skills: Optional[list[str]],
        tech_stack: Optional[list[str]],
    ) -> None:
        """Persist per-video metadata for future reuse."""

        now = datetime.now(timezone.utc).isoformat()
        await self._execute(
            """
            INSERT INTO youtube_video_metadata (video_url, summary, skills, tech_stack, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_url)
            DO UPDATE SET summary=excluded.summary,
                          skills=excluded.skills,
                          tech_stack=excluded.tech_stack,
                          updated_at=excluded.updated_at
            """,
            video_url,
            summary or "",
            _json_dumps(skills or []),
            _json_dumps(tech_stack or []),
            now,
            now,
        )

    async def get_youtube_video_metadata(self, video_url: str) -> Optional[dict[str, Any]]:
        """Return stored metadata for a specific YouTube video."""

        row = await self._fetchone(
            "SELECT summary, skills, tech_stack FROM youtube_video_metadata WHERE video_url = ?",
            video_url,
        )
        if not row:
            return None
        return {
            "summary": row["summary"],
            "skills": json.loads(row["skills"]) if row["skills"] else [],
            "tech_stack": json.loads(row["tech_stack"]) if row["tech_stack"] else [],
        }

    async def save_oauth_credentials(self, provider: str, account: str, credentials: dict[str, Any]) -> None:
        """Upsert OAuth credentials for a provider/account combination."""

        now = datetime.now(timezone.utc).isoformat()
        await self._execute(
            """
            INSERT INTO oauth_tokens (provider, account, credentials, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(provider, account)
            DO UPDATE SET credentials=excluded.credentials, updated_at=excluded.updated_at
            """,
            provider,
            account,
            _json_dumps(credentials),
            now,
            now,
        )

    async def get_oauth_credentials(self, provider: str, account: str) -> Optional[dict[str, Any]]:
        """Fetch previously stored OAuth credentials."""

        row = await self._fetchone(
            "SELECT credentials FROM oauth_tokens WHERE provider = ? AND account = ?",
            provider,
            account,
        )
        if not row:
            return None
        return json.loads(row["credentials"])
