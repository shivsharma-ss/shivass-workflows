"""Introduce normalized analysis storage schema"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Connection

# revision identifiers, used by Alembic.
revision = "20240712_01_normalized_schema"
down_revision = None
branch_labels = None
depends_on = None


def _json_dumps(value: Any) -> str:
    def _default(obj: Any) -> Any:
        if hasattr(obj, "model_dump"):
            try:
                return obj.model_dump(mode="json")
            except TypeError:
                return obj.model_dump()
        if isinstance(obj, set):
            return list(obj)
        return str(obj)

    return json.dumps(value, default=_default)


def upgrade() -> None:
    from alembic import op  # type: ignore

    apply_schema(op.get_bind())


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    """Return the set of column names for ``table_name`` or an empty set if missing."""

    try:
        return {col["name"] for col in inspector.get_columns(table_name)}
    except sa.exc.NoSuchTableError:
        return set()


def apply_schema(connection: Connection) -> None:
    inspector = sa.inspect(connection)
    connection.execute(text("PRAGMA foreign_keys=ON"))

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                cv_doc_id TEXT NOT NULL,
                approval_token TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
    )

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS analysis_inputs (
                analysis_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY(analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
            )
            """
        )
    )

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS analysis_status_log (
                analysis_id TEXT NOT NULL,
                status TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                last_error TEXT,
                recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (analysis_id, recorded_at),
                FOREIGN KEY(analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
            )
            """
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_analysis_status_log_analysis_id ON analysis_status_log(analysis_id)"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_analysis_status_log_analysis_id_status ON analysis_status_log(analysis_id, status)"
        )
    )

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(analysis_id, artifact_type, version),
                FOREIGN KEY(analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
            )
            """
        )
    )
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_artifacts_analysis ON artifacts(analysis_id)"))

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS node_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id TEXT NOT NULL,
                node_name TEXT NOT NULL,
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                completed_at TEXT,
                state_before TEXT,
                output TEXT,
                error TEXT,
                FOREIGN KEY(analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
            )
            """
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_node_events_analysis_node ON node_events(analysis_id, node_name, started_at)"
        )
    )

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS youtube_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id TEXT,
                skill TEXT,
                query TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY(analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
            )
            """
        )
    )

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS youtube_videos (
                video_id TEXT PRIMARY KEY,
                title TEXT,
                url TEXT NOT NULL,
                channel_title TEXT,
                duration TEXT,
                view_count INTEGER,
                like_count INTEGER,
                fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
    )

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS youtube_query_results (
                query_id INTEGER NOT NULL,
                video_id TEXT NOT NULL,
                rank INTEGER NOT NULL,
                PRIMARY KEY(query_id, video_id),
                FOREIGN KEY(query_id) REFERENCES youtube_queries(id) ON DELETE CASCADE,
                FOREIGN KEY(video_id) REFERENCES youtube_videos(video_id) ON DELETE CASCADE
            )
            """
        )
    )

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS video_analyses (
                video_id TEXT NOT NULL,
                model TEXT NOT NULL,
                summary TEXT,
                key_points TEXT,
                difficulty_level TEXT,
                prerequisites TEXT,
                takeaways TEXT,
                skills TEXT,
                tech_stack TEXT,
                cached_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY(video_id, model),
                FOREIGN KEY(video_id) REFERENCES youtube_videos(video_id) ON DELETE CASCADE
            )
            """
        )
    )

    if inspector.has_table("oauth_tokens") and not inspector.has_table("oauth_tokens_legacy"):
        oauth_columns = _column_names(inspector, "oauth_tokens")
        legacy_layout = "credentials" in oauth_columns and "encrypted_credentials" not in oauth_columns
        if legacy_layout:
            connection.execute(text("ALTER TABLE oauth_tokens RENAME TO oauth_tokens_legacy"))
            inspector = sa.inspect(connection)

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS oauth_accounts (
                provider TEXT NOT NULL,
                account TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY(provider, account)
            )
            """
        )
    )

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS oauth_tokens (
                provider TEXT NOT NULL,
                account TEXT NOT NULL,
                version INTEGER NOT NULL,
                encrypted_credentials TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                expires_at TEXT,
                PRIMARY KEY(provider, account, version),
                FOREIGN KEY(provider, account) REFERENCES oauth_accounts(provider, account) ON DELETE CASCADE
            )
            """
        )
    )

    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS cache_entries (
                cache_key TEXT PRIMARY KEY,
                namespace TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                expires_at TEXT NOT NULL,
                last_accessed TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
    )
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_cache_entries_namespace ON cache_entries(namespace)"))

    connection.execute(text("DROP VIEW IF EXISTS analysis_latest"))
    connection.execute(
        text(
            """
            CREATE VIEW IF NOT EXISTS analysis_latest AS
            SELECT a.id AS analysis_id,
                   a.email AS email,
                   a.cv_doc_id AS cv_doc_id,
                   a.approval_token AS approval_token,
                   a.created_at AS created_at,
                   a.updated_at AS updated_at,
                   l.status AS status,
                   l.payload AS payload,
                   l.last_error AS last_error,
                   l.recorded_at AS recorded_at
              FROM analyses a
              JOIN (
                    SELECT analysis_id, MAX(recorded_at) AS recorded_at
                      FROM analysis_status_log
                  GROUP BY analysis_id
              ) latest
                ON latest.analysis_id = a.id
              JOIN analysis_status_log l
                ON l.analysis_id = latest.analysis_id
               AND l.recorded_at = latest.recorded_at
            """
        )
    )

    connection.execute(text("DROP VIEW IF EXISTS oauth_active"))
    connection.execute(
        text(
            """
            CREATE VIEW IF NOT EXISTS oauth_active AS
            SELECT o.provider,
                   o.account,
                   t.encrypted_credentials,
                   t.issued_at,
                   t.expires_at
              FROM oauth_accounts o
              JOIN (
                    SELECT provider, account, MAX(version) AS version
                      FROM oauth_tokens
                  GROUP BY provider, account
              ) latest
                ON latest.provider = o.provider
               AND latest.account = o.account
              JOIN oauth_tokens t
                ON t.provider = latest.provider
               AND t.account = latest.account
               AND t.version = latest.version
            """
        )
    )

    connection.execute(text("DROP VIEW IF EXISTS node_latest_output"))
    connection.execute(
        text(
            """
            CREATE VIEW IF NOT EXISTS node_latest_output AS
            SELECT analysis_id,
                   node_name,
                   output,
                   completed_at
              FROM (
                    SELECT *,
                           ROW_NUMBER() OVER (
                               PARTITION BY analysis_id, node_name
                               ORDER BY datetime(completed_at) DESC
                           ) AS rn
                      FROM node_events
                     WHERE completed_at IS NOT NULL
              ) ranked
             WHERE rn = 1
            """
        )
    )

    connection.execute(
        text(
            """
            CREATE TRIGGER IF NOT EXISTS trg_analysis_status_updated
            AFTER INSERT ON analysis_status_log
            BEGIN
                UPDATE analyses SET updated_at = NEW.recorded_at WHERE id = NEW.analysis_id;
            END;
            """
        )
    )

    if inspector.has_table("analysis_runs"):
        rows = connection.execute(
            text(
                "SELECT analysis_id, email, cv_doc_id, status, payload, approval_token, last_error, created_at, updated_at"
                "  FROM analysis_runs"
            )
        ).fetchall()
        for row in rows:
            analysis_id = row.analysis_id
            created_at = row.created_at or datetime.now(timezone.utc).isoformat()
            updated_at = row.updated_at or created_at
            payload = row.payload or "{}"
            try:
                payload_json = json.loads(payload)
            except json.JSONDecodeError:
                payload_json = {}
            connection.execute(
                text(
                    "INSERT OR REPLACE INTO analyses (id, email, cv_doc_id, approval_token, created_at, updated_at)"
                    " VALUES (:id, :email, :cv_doc_id, :approval_token, :created_at, :updated_at)"
                ),
                {
                    "id": analysis_id,
                    "email": row.email,
                    "cv_doc_id": row.cv_doc_id,
                    "approval_token": row.approval_token,
                    "created_at": created_at,
                    "updated_at": updated_at,
                },
            )
            connection.execute(
                text(
                    "INSERT OR REPLACE INTO analysis_inputs (analysis_id, payload, created_at)"
                    " VALUES (:analysis_id, :payload, :created_at)"
                ),
                {
                    "analysis_id": analysis_id,
                    "payload": _json_dumps(payload_json),
                    "created_at": created_at,
                },
            )
            connection.execute(
                text(
                    "INSERT OR REPLACE INTO analysis_status_log"
                    " (analysis_id, status, payload, last_error, recorded_at)"
                    " VALUES (:analysis_id, :status, :payload, :last_error, :recorded_at)"
                ),
                {
                    "analysis_id": analysis_id,
                    "status": row.status,
                    "payload": _json_dumps(payload_json),
                    "last_error": row.last_error,
                    "recorded_at": updated_at,
                },
            )

    if inspector.has_table("analysis_artifacts"):
        artifact_rows = connection.execute(
            text(
                "SELECT analysis_id, artifact_type, content, created_at"
                "  FROM analysis_artifacts"
            )
        ).fetchall()
        for row in artifact_rows:
            connection.execute(
                text(
                    "INSERT INTO artifacts (analysis_id, artifact_type, version, content, created_at)"
                    " VALUES (:analysis_id, :artifact_type, :version, :content, :created_at)"
                ),
                {
                    "analysis_id": row.analysis_id,
                    "artifact_type": row.artifact_type,
                    "version": 1,
                    "content": row.content,
                    "created_at": row.created_at or datetime.now(timezone.utc).isoformat(),
                },
            )

    if inspector.has_table("youtube_cache"):
        cache_rows = connection.execute(
            text("SELECT query, videos, created_at FROM youtube_cache")
        ).fetchall()
        ttl = timedelta(days=1)
        for row in cache_rows:
            created_at = row.created_at or datetime.now(timezone.utc).isoformat()
            try:
                created_dt = datetime.fromisoformat(created_at)
            except ValueError:
                created_dt = datetime.now(timezone.utc)
            expires_at = (created_dt + ttl).isoformat()
            connection.execute(
                text(
                    "INSERT OR REPLACE INTO cache_entries (cache_key, namespace, value, created_at, expires_at, last_accessed)"
                    " VALUES (:cache_key, :namespace, :value, :created_at, :expires_at, :last_accessed)"
                ),
                {
                    "cache_key": f"youtube:search:{row.query}",
                    "namespace": "youtube_search",
                    "value": row.videos,
                    "created_at": created_at,
                    "expires_at": expires_at,
                    "last_accessed": created_at,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO youtube_queries (analysis_id, skill, query, created_at)"
                    " VALUES (NULL, '', :query, :created_at)"
                ),
                {"query": row.query, "created_at": created_at},
            )
            query_id = connection.execute(
                text(
                    "SELECT id FROM youtube_queries WHERE query = :query"
                    " ORDER BY datetime(created_at) DESC LIMIT 1"
                ),
                {"query": row.query},
            ).scalar_one()
            try:
                videos = json.loads(row.videos)
            except json.JSONDecodeError:
                videos = []
            for rank, video in enumerate(videos, start=1):
                if isinstance(video, dict):
                    video_id = (
                        video.get("video_id")
                        or video.get("id")
                        or video.get("url")
                        or f"{row.query}:{rank}"
                    )
                    title = video.get("title") or ""
                    url = video.get("url") or (f"https://youtu.be/{video_id}" if video_id else "")
                    channel = video.get("channel_title") or video.get("channelTitle")
                    duration = video.get("duration")
                    view_count = video.get("view_count") or video.get("viewCount")
                    like_count = video.get("like_count") or video.get("likeCount")
                else:
                    video_id = f"{row.query}:{rank}"
                    title = ""
                    url = ""
                    channel = None
                    duration = None
                    view_count = None
                    like_count = None
                connection.execute(
                    text(
                        "INSERT OR IGNORE INTO youtube_videos (video_id, title, url, channel_title, duration, view_count, like_count, fetched_at)"
                        " VALUES (:video_id, :title, :url, :channel, :duration, :view_count, :like_count, :fetched_at)"
                    ),
                    {
                        "video_id": video_id,
                        "title": title,
                        "url": url or video_id,
                        "channel": channel,
                        "duration": duration,
                        "view_count": view_count,
                        "like_count": like_count,
                        "fetched_at": created_at,
                    },
                )
                connection.execute(
                    text(
                        "INSERT OR REPLACE INTO youtube_query_results (query_id, video_id, rank)"
                        " VALUES (:query_id, :video_id, :rank)"
                    ),
                    {"query_id": query_id, "video_id": video_id, "rank": rank},
                )

    if inspector.has_table("youtube_video_metadata"):
        video_rows = connection.execute(
            text("SELECT video_url, summary, skills, tech_stack, created_at, updated_at FROM youtube_video_metadata")
        ).fetchall()
        for row in video_rows:
            video_id = row.video_url or ""
            summary = row.summary or ""
            skills = row.skills or "[]"
            tech_stack = row.tech_stack or "[]"
            created_at = row.created_at or datetime.now(timezone.utc).isoformat()
            connection.execute(
                text(
                    "INSERT OR REPLACE INTO youtube_videos (video_id, title, url, channel_title, duration, view_count, like_count, fetched_at)"
                    " VALUES (:video_id, :title, :url, '', NULL, NULL, NULL, :fetched_at)"
                ),
                {
                    "video_id": video_id,
                    "title": summary[:120],
                    "url": video_id,
                    "fetched_at": row.updated_at or created_at,
                },
            )
            connection.execute(
                text(
                    "INSERT OR REPLACE INTO video_analyses (video_id, model, summary, key_points, difficulty_level, prerequisites, takeaways, skills, tech_stack, cached_at)"
                    " VALUES (:video_id, :model, :summary, NULL, NULL, NULL, NULL, :skills, :tech_stack, :cached_at)"
                ),
                {
                    "video_id": video_id,
                    "model": "default",
                    "summary": summary,
                    "skills": skills,
                    "tech_stack": tech_stack,
                    "cached_at": row.updated_at or created_at,
                },
            )

    if inspector.has_table("oauth_tokens_legacy"):
        legacy_columns = _column_names(inspector, "oauth_tokens_legacy")
        credential_column = "credentials" if "credentials" in legacy_columns else "encrypted_credentials"
        created_column = "created_at" if "created_at" in legacy_columns else "issued_at"
        updated_column = "updated_at" if "updated_at" in legacy_columns else created_column
        select_stmt = text(
            f"SELECT provider, account, {credential_column} AS credentials, {created_column} AS created_at, {updated_column} AS updated_at"
            "  FROM oauth_tokens_legacy"
        )
        token_rows = connection.execute(select_stmt).fetchall()
        for row in token_rows:
            created_at = row.created_at or datetime.now(timezone.utc).isoformat()
            updated_at = row.updated_at or created_at
            connection.execute(
                text(
                    "INSERT OR IGNORE INTO oauth_accounts (provider, account, created_at)"
                    " VALUES (:provider, :account, :created_at)"
                ),
                {"provider": row.provider, "account": row.account, "created_at": created_at},
            )
            connection.execute(
                text(
                    "INSERT OR REPLACE INTO oauth_tokens (provider, account, version, encrypted_credentials, issued_at, expires_at)"
                    " VALUES (:provider, :account, :version, :credentials, :issued_at, NULL)"
                ),
                {
                    "provider": row.provider,
                    "account": row.account,
                    "version": 1,
                    "credentials": row.credentials,
                    "issued_at": updated_at,
                },
            )

    for table_name in [
        "analysis_artifacts",
        "analysis_runs",
        "youtube_cache",
        "youtube_video_metadata",
    ]:
        if inspector.has_table(table_name):
            connection.execute(text(f"DROP TABLE IF EXISTS {table_name}"))

    if inspector.has_table("oauth_tokens_legacy"):
        connection.execute(text("DROP TABLE IF EXISTS oauth_tokens_legacy"))


def downgrade() -> None:
    raise NotImplementedError("Downgrades are not supported for this migration")
