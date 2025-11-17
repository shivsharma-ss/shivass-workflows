"""Persistence layer powered by SQLite via aiosqlite with Alembic migrations."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

import aiosqlite

from app.schemas import AnalysisStatus
from services.migrations import run_migrations

YOUTUBE_CACHE_TTL_SECONDS = 86400
DEFAULT_VIDEO_MODEL = "default"


def _json_default(value: Any) -> Any:
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


def _json_loads(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _json_loads_list(raw: Optional[str]) -> list[Any]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(value, list):
        return value
    return []


def _parse_datetime(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now(timezone.utc)


def _extract_video_id(video_url: str) -> str:
    parsed = urlparse(video_url)
    if parsed.hostname in {"youtu.be"}:
        return parsed.path.lstrip("/")
    if parsed.hostname and "youtube.com" in parsed.hostname:
        query = parse_qs(parsed.query)
        if "v" in query:
            return query["v"][0]
    if parsed.path:
        return parsed.path.rsplit("/", 1)[-1]
    return video_url


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
    """Async storage abstraction over SQLite with normalized schema."""

    def __init__(self, db_url: str):
        if not db_url.startswith("sqlite"):
            raise ValueError("Only SQLite URLs are supported in this reference implementation")
        path = db_url.split("///")[-1]
        self._db_path = Path(path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Run Alembic migrations idempotently."""

        async with self._init_lock:
            if self._initialized:
                return
            await asyncio.to_thread(run_migrations, self._db_path)
            self._initialized = True

    @asynccontextmanager
    async def _connection(self, *, row_factory: bool = False):
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            if row_factory:
                db.row_factory = aiosqlite.Row
            yield db

    async def _execute(self, query: str, *params: Any) -> None:
        async with self._connection() as db:
            await db.execute(query, params)
            await db.commit()

    async def _fetchone(self, query: str, *params: Any) -> Optional[aiosqlite.Row]:
        async with self._connection(row_factory=True) as db:
            async with db.execute(query, params) as cursor:
                return await cursor.fetchone()

    async def _fetchall(self, query: str, *params: Any) -> list[aiosqlite.Row]:
        async with self._connection(row_factory=True) as db:
            async with db.execute(query, params) as cursor:
                return await cursor.fetchall()

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> AnalysisRecord:
        payload = _json_loads(row["payload"])
        return AnalysisRecord(
            analysis_id=row["analysis_id"],
            email=row["email"],
            cv_doc_id=row["cv_doc_id"],
            status=AnalysisStatus(row["status"]),
            payload=payload,
            approval_token=row["approval_token"],
            last_error=row["last_error"],
            created_at=_parse_datetime(row["created_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
        )

    async def create_analysis(self, analysis_id: str, email: str, cv_doc_id: str, payload: dict[str, Any]) -> None:
        """Insert a new analysis with initial payload and status log."""

        now = datetime.now(timezone.utc).isoformat()
        payload_json = _json_dumps(payload)
        async with self._connection(row_factory=True) as db:
            await db.execute("BEGIN")
            await db.execute(
                """
                INSERT INTO analyses (id, email, cv_doc_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET email=excluded.email,
                                             cv_doc_id=excluded.cv_doc_id,
                                             updated_at=excluded.updated_at
                """,
                (analysis_id, email, cv_doc_id, now, now),
            )
            await db.execute(
                """
                INSERT OR REPLACE INTO analysis_inputs (analysis_id, payload, created_at)
                VALUES (?, ?, ?)
                """,
                (analysis_id, payload_json, now),
            )
            await db.execute(
                """
                INSERT INTO analysis_status_log (analysis_id, status, payload, last_error, recorded_at)
                VALUES (?, ?, ?, NULL, ?)
                """,
                (analysis_id, AnalysisStatus.PENDING.value, payload_json, now),
            )
            await db.commit()

    async def update_status(
        self,
        analysis_id: str,
        status: AnalysisStatus,
        payload: Optional[dict[str, Any]] = None,
        last_error: Optional[str] = None,
    ) -> None:
        """Append a new status log entry."""

        now = datetime.now(timezone.utc).isoformat()
        if payload is None:
            latest = await self._fetchone(
                """
                SELECT payload
                  FROM analysis_status_log
                 WHERE analysis_id = ?
              ORDER BY datetime(recorded_at) DESC
                 LIMIT 1
                """,
                analysis_id,
            )
            payload_json = latest["payload"] if latest else _json_dumps({})
        else:
            payload_json = _json_dumps(payload)
        await self._execute(
            """
            INSERT INTO analysis_status_log (analysis_id, status, payload, last_error, recorded_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            analysis_id,
            status.value,
            payload_json,
            last_error,
            now,
        )

    async def save_payload(self, analysis_id: str, payload: dict[str, Any]) -> None:
        """Record a payload-only update without changing status."""

        record = await self.get_analysis(analysis_id)
        status = record.status if record else AnalysisStatus.PENDING
        await self.update_status(analysis_id, status, payload=payload, last_error=record.last_error if record else None)

    async def set_approval_token(self, analysis_id: str, token: str) -> None:
        """Store the approval token so future callbacks can be validated."""

        await self._execute(
            "UPDATE analyses SET approval_token = ?, updated_at = datetime('now') WHERE id = ?",
            token,
            analysis_id,
        )

    async def get_analysis(self, analysis_id: str) -> Optional[AnalysisRecord]:
        """Fetch the latest snapshot for an analysis."""

        row = await self._fetchone(
            """
            SELECT * FROM analysis_latest WHERE analysis_id = ?
            """,
            analysis_id,
        )
        if not row:
            return None
        return self._row_to_record(row)

    async def list_analyses(
        self,
        *,
        limit: int = 50,
        status: Optional[AnalysisStatus] = None,
    ) -> list[AnalysisRecord]:
        """Return recent analyses optionally filtered by status."""

        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status.value)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        query = (
            "SELECT * FROM analysis_latest"
            f"{where} ORDER BY datetime(updated_at) DESC LIMIT ?"
        )
        params.append(limit)
        rows = await self._fetchall(query, *params)
        return [self._row_to_record(row) for row in rows]

    async def get_status_history(self, analysis_id: str) -> list[dict[str, Any]]:
        """Return chronological status history for debugging."""

        rows = await self._fetchall(
            """
            SELECT status, payload, last_error, recorded_at
              FROM analysis_status_log
             WHERE analysis_id = ?
             ORDER BY datetime(recorded_at)
            """,
            analysis_id,
        )
        history: list[dict[str, Any]] = []
        for row in rows:
            history.append(
                {
                    "status": row["status"],
                    "payload": _json_loads(row["payload"]),
                    "last_error": row["last_error"],
                    "recorded_at": row["recorded_at"],
                }
            )
        return history

    async def save_artifact(self, analysis_id: str, artifact_type: str, content: Any) -> None:
        """Persist intermediate artifact content keyed by analysis and type."""

        serialized = content if isinstance(content, str) else _json_dumps(content)
        async with self._connection(row_factory=True) as db:
            async with db.execute(
                """
                SELECT COALESCE(MAX(version), 0) AS max_version
                  FROM artifacts
                 WHERE analysis_id = ? AND artifact_type = ?
                """,
                (analysis_id, artifact_type),
            ) as cursor:
                row = await cursor.fetchone()
            next_version = (row["max_version"] if row else 0) + 1
            await db.execute(
                """
                INSERT INTO artifacts (analysis_id, artifact_type, version, content, created_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                """,
                (analysis_id, artifact_type, next_version, serialized),
            )
            await db.commit()

    async def get_artifact(self, analysis_id: str, artifact_type: str) -> Optional[str]:
        """Return the stored artifact payload, if any (latest version)."""

        row = await self._fetchone(
            """
            SELECT content
              FROM artifacts
             WHERE analysis_id = ? AND artifact_type = ?
          ORDER BY version DESC
             LIMIT 1
            """,
            analysis_id,
            artifact_type,
        )
        return row["content"] if row else None

    async def list_artifacts(self, analysis_id: str) -> list[dict[str, Any]]:
        """Return all artifacts captured for an analysis sorted by recency."""

        rows = await self._fetchall(
            """
            SELECT artifact_type, content, created_at, version
              FROM artifacts
             WHERE analysis_id = ?
          ORDER BY datetime(created_at) DESC, version DESC
            """,
            analysis_id,
        )
        artifacts: list[dict[str, Any]] = []
        for row in rows:
            artifacts.append(
                {
                    "artifact_type": row["artifact_type"],
                    "content": row["content"],
                    "created_at": row["created_at"],
                    "version": row["version"],
                }
            )
        return artifacts

    async def save_youtube_cache(self, query: str, videos: list[dict[str, Any]]) -> None:
        """Persist rendered YouTube results so future runs can reuse them."""

        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(seconds=YOUTUBE_CACHE_TTL_SECONDS)).isoformat()
        payload = _json_dumps(videos)
        cache_key = f"youtube:search:{query}"
        async with self._connection(row_factory=True) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO cache_entries (cache_key, namespace, value, created_at, expires_at, last_accessed)
                VALUES (?, 'youtube_search', ?, ?, ?, ?)
                """,
                (cache_key, payload, now.isoformat(), expires_at, now.isoformat()),
            )
            await db.execute(
                """
                INSERT INTO youtube_queries (analysis_id, skill, query, created_at)
                VALUES (NULL, NULL, ?, ?)
                """,
                (query, now.isoformat()),
            )
            async with db.execute(
                """
                SELECT id FROM youtube_queries
                 WHERE query = ?
              ORDER BY datetime(created_at) DESC
                 LIMIT 1
                """,
                (query,),
            ) as cursor:
                query_row = await cursor.fetchone()
            query_id = query_row["id"] if query_row else None
            if query_id is not None:
                for rank, video in enumerate(videos, start=1):
                    video_id = _extract_video_id(video.get("url") or video.get("video_id") or "") or f"{query}:{rank}"
                    title = video.get("title") or ""
                    channel = video.get("channel_title") or video.get("channelTitle")
                    duration = video.get("duration")
                    view_count = video.get("view_count") or video.get("viewCount")
                    like_count = video.get("like_count") or video.get("likeCount")
                    await db.execute(
                        """
                        INSERT OR IGNORE INTO youtube_videos (video_id, title, url, channel_title, duration, view_count, like_count, fetched_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            video_id,
                            title,
                            video.get("url") or (f"https://youtu.be/{video_id}" if video_id else ""),
                            channel,
                            duration,
                            int(view_count) if view_count else None,
                            int(like_count) if like_count else None,
                            now.isoformat(),
                        ),
                    )
                    await db.execute(
                        """
                        INSERT OR REPLACE INTO youtube_query_results (query_id, video_id, rank)
                        VALUES (?, ?, ?)
                        """,
                        (query_id, video_id, rank),
                    )
            await db.commit()

    async def get_youtube_cache(self, query: str, max_age_seconds: int = 86400) -> Optional[list[dict[str, Any]]]:
        """Return cached YouTube entries if still fresh."""

        cache_key = f"youtube:search:{query}"
        if max_age_seconds < 0:
            return None
        row = await self._fetchone(
            "SELECT value, created_at, expires_at FROM cache_entries WHERE cache_key = ?",
            cache_key,
        )
        if not row:
            return None
        now = datetime.now(timezone.utc)
        created_at = _parse_datetime(row["created_at"])
        expires_at = _parse_datetime(row["expires_at"])
        if now > expires_at:
            return None
        if max_age_seconds >= 0 and now - created_at > timedelta(seconds=max_age_seconds):
            return None
        await self._execute(
            "UPDATE cache_entries SET last_accessed = ? WHERE cache_key = ?",
            datetime.now(timezone.utc).isoformat(),
            cache_key,
        )
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return None

    async def save_youtube_video_metadata(
        self,
        video_url: str,
        *,
        summary: Optional[str] = None,
        key_points: Optional[list[str]] = None,
        difficulty_level: Optional[str] = None,
        prerequisites: Optional[list[str]] = None,
        takeaways: Optional[list[str]] = None,
        skills: Optional[list[str]] = None,
        tech_stack: Optional[list[str]] = None,
        model: str = DEFAULT_VIDEO_MODEL,
    ) -> None:
        """Persist per-video metadata (Gemini or otherwise) for future reuse."""

        if not video_url:
            return
        video_id = _extract_video_id(video_url)
        now = datetime.now(timezone.utc).isoformat()
        serialized_key_points = _json_dumps(key_points) if key_points is not None else None
        serialized_prereqs = _json_dumps(prerequisites) if prerequisites is not None else None
        serialized_takeaways = _json_dumps(takeaways) if takeaways is not None else None
        serialized_skills = _json_dumps(skills) if skills is not None else None
        serialized_stack = _json_dumps(tech_stack) if tech_stack is not None else None

        async with self._connection() as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO youtube_videos (video_id, title, url, channel_title, duration, view_count, like_count, fetched_at)
                VALUES (?, ?, ?, NULL, NULL, NULL, NULL, ?)
                """,
                (
                    video_id,
                    (summary or "")[:120],
                    video_url or video_id,
                    now,
                ),
            )
            await db.execute(
                """
                INSERT INTO video_analyses (
                    video_id,
                    model,
                    summary,
                    key_points,
                    difficulty_level,
                    prerequisites,
                    takeaways,
                    skills,
                    tech_stack,
                    cached_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id, model) DO UPDATE SET
                    summary = COALESCE(excluded.summary, video_analyses.summary),
                    key_points = COALESCE(excluded.key_points, video_analyses.key_points),
                    difficulty_level = COALESCE(excluded.difficulty_level, video_analyses.difficulty_level),
                    prerequisites = COALESCE(excluded.prerequisites, video_analyses.prerequisites),
                    takeaways = COALESCE(excluded.takeaways, video_analyses.takeaways),
                    skills = COALESCE(excluded.skills, video_analyses.skills),
                    tech_stack = COALESCE(excluded.tech_stack, video_analyses.tech_stack),
                    cached_at = excluded.cached_at
                """,
                (
                    video_id,
                    model,
                    summary,
                    serialized_key_points,
                    difficulty_level,
                    serialized_prereqs,
                    serialized_takeaways,
                    serialized_skills,
                    serialized_stack,
                    now,
                ),
            )
            await db.commit()

    async def get_youtube_video_metadata(self, video_url: str) -> Optional[dict[str, Any]]:
        """Return stored metadata for a specific YouTube video."""

        video_id = _extract_video_id(video_url)
        row = await self._fetchone(
            """
            SELECT summary, key_points, difficulty_level, prerequisites, takeaways, skills, tech_stack
              FROM video_analyses
             WHERE video_id = ? AND model = ?
            """,
            video_id,
            DEFAULT_VIDEO_MODEL,
        )
        if not row:
            return None
        return {
            "summary": row["summary"],
            "key_points": _json_loads_list(row["key_points"]),
            "difficulty_level": row["difficulty_level"],
            "prerequisites": _json_loads_list(row["prerequisites"]),
            "takeaways": _json_loads_list(row["takeaways"]),
            "skills": _json_loads_list(row["skills"]),
            "tech_stack": _json_loads_list(row["tech_stack"]),
        }

    async def list_videos_missing_analysis(
        self,
        *,
        limit: int = 50,
        resume_after: Optional[str] = None,
    ) -> list[dict[str, str]]:
        """Return videos that lack structured Gemini analysis fields."""

        limit = max(1, min(limit, 500))
        conditions = [
            "a.video_id IS NULL",
            "a.key_points IS NULL OR a.key_points = '' OR a.key_points = '[]'",
            "a.difficulty_level IS NULL OR a.difficulty_level = ''",
            "a.prerequisites IS NULL OR a.prerequisites = '' OR a.prerequisites = '[]'",
            "a.takeaways IS NULL OR a.takeaways = '' OR a.takeaways = '[]'",
        ]
        params: list[Any] = [DEFAULT_VIDEO_MODEL]
        resume_clause = ""
        if resume_after:
            resume_clause = "AND v.video_id > ?"
            params.append(resume_after)
        query = f"""
            SELECT v.video_id, v.url
              FROM youtube_videos v
              LEFT JOIN video_analyses a
                ON a.video_id = v.video_id AND a.model = ?
             WHERE ({' OR '.join(conditions)})
               {resume_clause}
          ORDER BY v.video_id
             LIMIT ?
        """
        params.append(limit)
        rows = await self._fetchall(query, *params)
        pending: list[dict[str, str]] = []
        for row in rows:
            url = row["url"] or f"https://youtu.be/{row['video_id']}"
            pending.append({"video_id": row["video_id"], "url": url})
        return pending

    async def save_oauth_credentials(self, provider: str, account: str, credentials: dict[str, Any]) -> None:
        """Version OAuth credentials for a provider/account combination."""

        now = datetime.now(timezone.utc).isoformat()
        async with self._connection(row_factory=True) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO oauth_accounts (provider, account, created_at)
                VALUES (?, ?, ?)
                """,
                (provider, account, now),
            )
            async with db.execute(
                """
                SELECT COALESCE(MAX(version), 0) AS max_version
                  FROM oauth_tokens
                 WHERE provider = ? AND account = ?
                """,
                (provider, account),
            ) as cursor:
                row = await cursor.fetchone()
            next_version = (row["max_version"] if row else 0) + 1
            await db.execute(
                """
                INSERT INTO oauth_tokens (provider, account, version, encrypted_credentials, issued_at, expires_at)
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (provider, account, next_version, _json_dumps(credentials), now),
            )
            await db.commit()

    async def get_oauth_credentials(self, provider: str, account: str) -> Optional[dict[str, Any]]:
        """Fetch the latest stored OAuth credentials."""

        row = await self._fetchone(
            "SELECT encrypted_credentials FROM oauth_active WHERE provider = ? AND account = ?",
            provider,
            account,
        )
        if not row:
            return None
        return _json_loads(row["encrypted_credentials"])

    async def record_node_event(
        self,
        analysis_id: str,
        node_name: str,
        state_before: Optional[dict[str, Any]] = None,
        output: Optional[dict[str, Any]] = None,
        *,
        started_at: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Persist execution telemetry for a LangGraph node."""

        started = started_at or datetime.now(timezone.utc).isoformat()
        completed = datetime.now(timezone.utc).isoformat()
        await self._execute(
            """
            INSERT INTO node_events (analysis_id, node_name, started_at, completed_at, state_before, output, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            analysis_id,
            node_name,
            started,
            completed,
            _json_dumps(state_before or {}),
            _json_dumps(output or {}),
            error,
        )

    async def list_node_events(self, analysis_id: str) -> list[dict[str, Any]]:
        """Return recorded node events for an analysis ordered by start time."""

        rows = await self._fetchall(
            """
            SELECT node_name, started_at, completed_at, state_before, output, error
              FROM node_events
             WHERE analysis_id = ?
          ORDER BY datetime(started_at)
            """,
            analysis_id,
        )
        events: list[dict[str, Any]] = []
        for row in rows:
            events.append(
                {
                    "node_name": row["node_name"],
                    "started_at": row["started_at"],
                    "completed_at": row["completed_at"],
                    "state_before": _json_loads(row["state_before"]),
                    "output": _json_loads(row["output"]),
                    "error": row["error"],
                }
            )
        return events

    async def touch_cache_entry(self, cache_key: str, namespace: str, value: Any, ttl_seconds: int) -> None:
        """Generic helper for writing cache entries (primarily for tests)."""

        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
        await self._execute(
            """
            INSERT OR REPLACE INTO cache_entries (cache_key, namespace, value, created_at, expires_at, last_accessed)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            cache_key,
            namespace,
            _json_dumps(value),
            now.isoformat(),
            expires_at,
            now.isoformat(),
        )
