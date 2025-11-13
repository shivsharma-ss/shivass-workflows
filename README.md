# CV–JD Alignment Orchestrator

Agentic workflow that ingests a candidate CV from Google Docs, reconciles it with the target Job Description, suggests bespoke tutorials/projects to close gaps, and manages a reviewer approval loop before rewriting the document. The stack is FastAPI + LangGraph on top of OpenAI Structured Outputs, with Google Workspace, Gmail, YouTube, Redis, and SQLite integrations.

## Highlights
- Google Drive export plus safe Docs `batchUpdate` prepends so CVs keep their original content below the generated recommendations.
- LangGraph state machine orchestrates `ingest → drive_export → merge_jd → jd_analyze → cv_score → build_queries → yt_branch → mvp_projects → collect → email → wait_approval → docs_apply → recalc`.
- Deterministic LLM calls via Pydantic schemas (analysis, scoring, tutorial personalization, MVP plan).
- YouTube search with quota tracking, caching (Redis + SQLite), and Gemini-powered tutorial analysis (optional).
- Quota-aware YouTube client enforces `YOUTUBE_QUOTA_DAILY` so we fail fast before blowing through API limits.
- Next.js 14 dashboard (`frontend/`) handles submissions, persists light/dark themes, manages live run history, and now ships an accessible YouTube-channel boosting UI so reviewers can favor trusted creators before the run starts.
- Gmail sending supports either stored OAuth tokens (per reviewer) or a service account fallback with SMTP backup.
- Test pyramid keeps regressions in check: backend contract + storage suites (Pytest) cover Gmail/OAuth/cache paths, while the frontend pairs Vitest component coverage with Playwright end-to-end runs under `frontend/tests/e2e`.
- Persistence layer keeps analysis payloads, artifacts, tutorial cache, OAuth tokens, and quota usage inside `data/orchestrator.db`.

## Requirements
- Python 3.11+
- OpenAI API key (required for the LangGraph nodes)
- Google Cloud service account with Drive & Docs scopes
- Gmail account with OAuth consent for the Gmail API
- YouTube Data API key (optional but enables tutorial search)
- Gemini API key (optional; enriches tutorial metadata)
- Redis (optional; without it the cache falls back to in-memory)

## Setup
```bash
cp .env.example .env
# edit .env with OpenAI, Google, Gmail, Redis, and optional Gemini/YouTube keys

python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
uvicorn src.app.main:create_app --factory --reload
```

`docker-compose.yml` can also spin up Redis alongside the API container:
```bash
docker compose up --build
```
The FastAPI app still writes to `sqlite+aiosqlite:///./data/orchestrator.db`; Redis just unlocks caching + OAuth state without any extra services.

## Environment variables
| Variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | Required for LangGraph nodes (analysis, scoring, personalization). |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Path to the Drive/Docs service account JSON. |
| `GOOGLE_WORKSPACE_SUBJECT` | Optional domain-wide delegation user. Leave blank if not using Workspace impersonation. |
| `GMAIL_SENDER` | Email address the workflow uses when sending reviewer notifications. |
| `GOOGLE_OAUTH_CLIENT_ID/SECRET/REDIRECT_URI` | Enables Gmail OAuth so the app can send on behalf of `GMAIL_SENDER`. |
| `SMTP_*` | Optional SMTP fallback if Gmail API is unavailable. |
| `REDIS_URL` | Cache + OAuth state backend (defaults to `redis://localhost:6379/0`). |
| `DATABASE_URL` | Must remain an SQLite URL today (default `sqlite+aiosqlite:///./data/orchestrator.db`). |
| `FRONTEND_BASE_URL` | Base URL exposed to reviewers when they reply/approve. |
| `CORS_ORIGINS` | Comma-separated origins allowed to call the API (default `http://localhost:3000`). |
| `YOUTUBE_API_KEY` | Enables tutorial discovery and ranking. |
| `YOUTUBE_QUOTA_DAILY` | Daily quota units the YouTube client may spend before it fails fast (default `10000`). |
| `GEMINI_API_KEY` | Enables tutorial enrichment via Gemini. |
| `REVIEW_SECRET` | Secret for signing reviewer approval tokens. |

See `.env.example` for the complete list.

Frontend-specific env vars belong in `frontend/.env.local`:
```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8001
```
That variable is only needed when the dashboard is served from a different origin than the FastAPI backend.

## Credential walkthrough
1. **Google Drive / Docs service account**  
   - In Google Cloud Console enable the Drive and Docs APIs, create a service account, download `service-account.json`, and share the candidate CV docs/folder with that account.  
   - Populate `GOOGLE_SERVICE_ACCOUNT_FILE`. Set `GOOGLE_WORKSPACE_SUBJECT` only if you have Workspace-wide delegation.
2. **Gmail OAuth**  
   - Enable Gmail API, create an OAuth 2.0 *Web application* client with origin `http://localhost:8001` and redirect `http://localhost:8001/oauth/google/callback`.  
   - Set `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI`.  
   - Start the consent flow via `http://localhost:8001/oauth/google/start`. Approving generates a refresh token stored in SQLite via `OAuthTokenStore`.
3. **OpenAI / Gemini / YouTube**  
   - `OPENAI_API_KEY` is mandatory.  
   - `GEMINI_API_KEY` and `YOUTUBE_API_KEY` are optional but unlock tutorial summaries + MVP generation.  
   - Redis is recommended for caching YouTube responses and OAuth state (`CacheService` gracefully falls back to memory if unset).

## Running the stack
### Manual (venv)
```bash
uvicorn src.app.main:create_app --factory --reload --port 8001
```
### Docker Compose
```bash
docker compose up --build api
```
This mounts the repo into `/app`, passes `.env`, and links the Redis container for caching/state. Stop the stack with `docker compose down`.

### Frontend dashboard
```bash
cd frontend
npm install
npm run dev
```

By default the dashboard proxies to the API origin it is served from. When running the frontend on a different port, export
`NEXT_PUBLIC_API_BASE_URL` (for example `http://localhost:8001`) so the UI can reach the FastAPI service.

Key UI capabilities:
- CV + JD inputs sanitize pasted Google Docs URLs so the API always receives a clean `docId`.
- Preferred YouTube channels now have a chip-based editor with boost sliders (0.5–2x) so you can bias the tutorial ranking toward trusted creators.
- Theme selection persists via the `ThemeProvider`, and the dashboard keeps the latest run feedback + artifacts available without reloading.

## Workflow lifecycle
1. `POST /v1/analyses` with `{ email, cvDocId, jobDescription?|jobDescriptionUrl?, preferredYoutubeChannels? }`. Returns an `analysisId`.  
   The dashboard preloads trusted channels (freeCodeCamp.org, Tech With Tim, TechWithTim, IBM Technology) with a mild boost—edit or remove them before submission if you prefer other creators. Leaving the list empty disables boosts entirely.
2. LangGraph immediately records the payload, exports the CV via Drive, ingests the JD, and runs the analysis chain.
3. When a reviewer decision is required, the workflow pauses in `awaiting_approval` and sends an email containing a signed token.
4. Reviewer resumes the run by POSTing to `/review/approve` with the `analysisId` + `token`.
5. The Next.js dashboard in `frontend/` polls `GET /v1/analyses` + `GET /v1/analyses/{analysis_id}` and surfaces artifacts.

## Testing & utilities

### Backend (pytest + coverage)
- `pytest` — runs unit + integration suites (services, LangGraph runner, API contracts) with `--cov=src --cov-fail-under=90`. Coverage now omits the pure integration shims (`app/main.py`, `orchestrator/graph.py`, and the Google/LLM adapters) so we measure only the code paths we can deterministically exercise.
- `pytest src/tests/services` — fast contract checks for FastAPI routes, DB schema parity, and workflow/ranking round-trips if you only need those smoke tests.
- Optional Gmail smoke test (`src/tests/test_email_smoke.py`) stays skipped unless `EMAIL_SMOKE_RECIPIENT` is set so CI never attempts to send real messages.

### Frontend (Vitest + Playwright)
- `cd frontend && npm run lint && npm run type-check` — keeps Next.js + TypeScript healthy.
- `npm run test` — Vitest + Testing Library component coverage (AnalysisForm, ArtifactViewer, theme system, utilities) now enforces 90/75/90/90 thresholds for statements/branches/lines/functions, and bundles helper-unit coverage directly in `analysis-form.test.jsx`.
- `npm run test:e2e` — Playwright workflow that spins up `next dev`, stubs the API, submits the CV form, manipulates channel boosts, validates theme persistence, and keeps the run lightweight enough for CI (no artifact inspection post-reload).

### Smoke + CLI helpers
- `python -m scripts.clear_tokens` (or `scripts/clear_tokens.py -- default args`) clears Redis + SQLite OAuth tokens; tests cover success/failure paths so it’s safe to run against temp DBs.
- Real Gmail send test only runs when `EMAIL_SMOKE_RECIPIENT` is configured.
- `frontend/` houses the dashboard (`npm install && npm run dev`). `submit-cv.html` simply links there for legacy bookmarks.

### Future enhancements
- Mutation/property testing over `services.ranking` heuristics to fuzz-score regressions.
- Record/replay external API contracts (Gmail, Google Docs, YouTube) via something like VCR.py to detect upstream schema shifts without live calls.

## Project layout
```
src/
  app/            # FastAPI app factory, routers, schemas, settings
  orchestrator/   # LangGraph nodes, state, runner, and exceptions
  services/       # Integrations (Drive, Docs, Gmail, OAuth, LLM, YouTube, Gemini, storage, cache)
  tests/          # Pytest coverage for services, nodes, and API glue
scripts/          # Operational helpers (e.g., clear_tokens.py)
data/             # SQLite artifacts (gitignored)
docker-compose.yml
submit-cv.html
```

## API reference
- `POST /v1/analyses` — start a CV alignment run.
- `GET /v1/analyses` — list the most recent runs with status metadata.
- `GET /v1/analyses/{analysisId}` — fetch the latest status/payload snapshot.
- `GET /v1/analyses/{analysisId}/artifacts` — download stored intermediate artifacts.
- `POST /review/approve` — validate the signed token and resume a paused run.
- `GET /oauth/google/start` / `GET /oauth/google/callback` — Gmail OAuth helper endpoints.

## LinkedIn Post (copy/paste)
🚀 Built the **CV–JD Alignment Orchestrator** to show how I approach agentic workflows that bridge AI reasoning with real hiring ops.

**Why recruiters should care:** the system ingests a candidate’s Google Doc CV, compares it with the live job posting, surfaces tailored study plan + MVP projects, and loops reviewers back in via Gmail before anything ships. Faster signal, less manual triage.

**Why engineers in my network might enjoy it:** it’s an end-to-end playground covering LangGraph state machines, FastAPI, Google Workspace APIs, OpenAI structured outputs, a Next.js 14 dashboard, Vitest + Playwright coverage, and Redis-backed caching. Clone it, swap your keys, and you have a repeatable job-search co-pilot.

**Tech stack highlights**
- FastAPI + LangGraph orchestrating ingest → scoring → tutorial query → reviewer approval → Docs rewrite.
- Gmail API + OAuth, Drive/Docs service accounts, and Redis/SQLite persistence.
- Next.js 14 App Router UI with an accessible chip-based editor for prioritizing YouTube creators plus light/dark theming.
- Test pyramid: Pytest contract suites, Vitest component coverage, Playwright e2e smoke.

**What I learned shipping this**
- Designing deterministic LLM prompts + Pydantic schemas keeps LangGraph transitions predictable.
- Coordinating Google OAuth tokens, Redis cache, and SQLite artifacts surfaces real-world auth edge cases early.
- Opinionated UX (auto-parsing Google Doc IDs, boost sliders, optimistic toasts) dramatically reduces bad submissions.

**Use cases**
- Recruiters or hiring partners who want an internal tool that scores CV vs JD fit and prescribes upskilling plans.
- Career coaches accelerating mentees with personalized tutorial playlists and MVP briefs.
- Individual job seekers who want an automated reviewer + study buddy before every application.

**Target audience**
1. Talent teams / recruiters evaluating my portfolio work and looking for builders who can own AI-enabled workflows end to end.
2. Fellow engineers, bootcamp peers, and job seekers who want to fork the repo and adapt the workflow to their niche.

DM me if you’d like a walkthrough or want to pair on extending the pipeline (multi-model support, ATS exports, etc.).

`#fastapi #langgraph #nextjs #jobsearch #aiagents #opensource #portfolio`

That’s the current state of the orchestrator. Update the `.env`, run the FastAPI server, and use the provided HTML form or your own frontend to drive analyses end-to-end.
