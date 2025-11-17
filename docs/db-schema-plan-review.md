# Database Schema Plan Review

## Summary
- The shipping SQLite schema still revolves around monolithic `analysis_runs`, single-row `analysis_artifacts`, ad-hoc YouTube caches, and a flat `oauth_tokens` table; no historical logging or foreign keys have been introduced since the earlier plan was drafted.【F:src/services/storage.py†L69-L125】【F:src/services/storage.py†L261-L411】
- In-memory/Redis caching now fronts many hot paths, but the backing tables continue to store opaque JSON without TTLs or access metadata, leaving the plan’s normalization goals largely unmet.【F:src/services/cache.py†L1-L79】【F:src/services/storage.py†L314-L380】
- Tooling (tests, scripts, bundled DB) still assumes the legacy layout, so any redesign must include data migration, updated fixtures, and operational scripts alongside the schema changes.【F:src/tests/services/test_db_schema.py†L13-L38】【F:scripts/clear_tokens.py†L1-L38】

## Current storage layout snapshot

### `analysis_runs`
`StorageService.initialize` still creates a wide `analysis_runs` row that holds metadata, status, payload, approval token, and last error in one place. Status updates overwrite the JSON blob and last error, so there is no history or partial updates, exactly as the original critique described.【F:src/services/storage.py†L69-L209】

### Artifacts
Artifacts remain a single row per `(analysis_id, artifact_type)` with the latest payload replacing earlier content. There are no foreign keys to the parent run, no versioning, and no ordering beyond `created_at` timestamps that are rewritten on every upsert.【F:src/services/storage.py†L84-L312】

### YouTube persistence
Both `youtube_cache` and `youtube_video_metadata` persist JSON strings. Cache freshness is evaluated in Python by parsing the stored timestamp, and there is no TTL/last-access metadata beyond the rewritten `created_at`. The split tables mirror the duplication called out in the plan.【F:src/services/storage.py†L314-L380】

### OAuth tokens
The tokens table still stores one credential blob per provider/account pair and rewrites it in-place. The cleanup script truncates the table wholesale, reinforcing that there is no rotation history or per-version retention.【F:src/services/storage.py†L116-L411】【F:scripts/clear_tokens.py†L1-L38】

### Cache layer
A new `CacheService` adds an in-memory/Redis TTL cache, but it only fronts the existing tables. There is still no persistent cache namespace, TTL, or access metadata in SQLite, so the general caching concerns from the plan remain unresolved.【F:src/services/cache.py†L22-L79】【F:src/services/storage.py†L314-L380】

### Schema guards
Regression tests continue to assert that the production SQLite file exposes the legacy tables, so the runtime and test fixtures have not been updated toward the proposed schema yet.【F:src/tests/services/test_db_schema.py†L13-L38】

## Assessment of the earlier redesign plan

### Core analyses + status log
The recommendation to split immutable run metadata (`analyses`) from an append-only status log is still applicable. When implementing it, we need to carry over `approval_token` (currently stored on `analysis_runs`) and decide whether `last_error` belongs in the status log or a sibling table so that callbacks and approvals keep working.【F:src/services/storage.py†L69-L209】 Additionally, `StorageService.create_analysis` relies on `INSERT OR REPLACE`; moving to normalized tables should ensure we don’t accidentally drop existing status history when re-running initialization logic.

### Artifacts and versioning
Supporting multiple artifact versions per run/type remains a gap. The proposed `(analysis_id, artifact_type, version)` key aligns with how `save_artifact` is called, but we will need to change the upsert logic so new versions append rather than overwrite, and add foreign keys back to `analyses` once that table exists.【F:src/services/storage.py†L261-L312】 Consider also storing a content MIME/type column because today we mix raw strings and JSON.

### YouTube and Gemini data
The plan to normalize YouTube queries, videos, and Gemini analyses is still relevant. Since we now depend on `CacheService` for short-lived responses, the persistent tables should complement it by capturing TTL/`last_accessed` fields so eviction can be data-driven. Align the schema with `YouTubeService._persist`, which currently writes summaries and descriptions, to avoid duplicating storage in both cache and metadata tables.【F:src/services/youtube.py†L57-L112】【F:src/services/storage.py†L314-L380】【F:src/services/cache.py†L22-L79】

### OAuth accounts and token history
Versioned tokens per provider/account would immediately help with auditability. Migrating here must also update `scripts/clear_tokens.py` (and any tests) to truncate the new tables or expire only the active version, otherwise the cleanup workflow will fail.【F:src/services/storage.py†L116-L411】【F:scripts/clear_tokens.py†L1-L38】 Consider capturing when a token was last used to support proactive rotation.

### Unified cache entries
A general `cache_entries` table is still absent. If we add it, we should integrate it with `CacheService` so Redis and SQLite stay in sync or share eviction policies. The table should mirror the TTL semantics already exposed via `CacheService.set` to avoid diverging behavior between memory and disk caches.【F:src/services/cache.py†L22-L79】

### Node event logging
No node-level telemetry is persisted today, so introducing `node_events` (and possibly `analysis_inputs`) would significantly improve debuggability. Ensure the orchestration layer emits events when nodes run; today `StorageService` has no hooks for that, so new APIs (e.g., `record_node_event`) would be required.【F:src/services/storage.py†L60-L411】【F:src/orchestrator/state.py†L22-L89】

### Migration tooling and observability
We still lack a migration framework; schema creation happens ad-hoc during startup. The bundled SQLite file (`data/orchestrator.db`) and the schema regression test will need to be regenerated after migrations run. Introducing Alembic or yoyo would let us evolve the schema without hand-editing SQL, and we should add diagnostics (CLI endpoints, FastAPI routes) once the new tables exist.【F:src/services/storage.py†L60-L128】【F:src/tests/services/test_db_schema.py†L13-L38】

## Suggested next steps
1. **Inventory the runtime touchpoints.** Document how each `StorageService` method maps to the proposed normalized tables so refactors cover orchestrator nodes, OAuth flows, and YouTube persistence.
2. **Introduce a migration scaffold.** Add Alembic (or similar) so new tables, triggers, and data backfills are tracked and repeatable across environments.
3. **Implement normalized tables incrementally.** Start with `analyses`/`analysis_status_log`, then port artifacts, YouTube data, OAuth tokens, and caching layers, updating application code and scripts as each piece lands.
4. **Add observability.** Once node events are persisted, expose an API or CLI to inspect a run’s timeline to make the new history useful to developers and operators.
