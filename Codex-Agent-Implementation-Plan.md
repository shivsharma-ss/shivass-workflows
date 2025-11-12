# Codex Agent Implementation Plan — CV–JD Alignment Orchestrator (LangGraph + FastAPI)

Purpose: rebuild your n8n workflow as an **agentic, code-first graph** that preserves the same steps, APIs, and outputs. This playbook gives precise prompts, code references, libraries, test strategy, and backtracking procedures for a **Codex‑style coding agent** to implement the system end‑to‑end.

---

## 0) Sources used

- OpenAI: **Structured Outputs** (JSON‑schema adherence) — <https://platform.openai.com/docs/guides/structured-outputs>
- OpenAI: **JSON mode** overview — <https://platform.openai.com/docs/guides/structured-outputs/json-mode>
- OpenAI blog: Introducing Structured Outputs — <https://openai.com/index/introducing-structured-outputs-in-the-api/>
- **LangGraph** docs — <https://langchain-ai.github.io/langgraph/>
- Google Drive API: **files.export** (10 MB limit) — <https://developers.google.com/workspace/drive/api/reference/rest/v3/files/export>
- Drive guide: download and export — <https://developers.google.com/workspace/drive/api/guides/manage-downloads>
- Google Docs API: **documents.batchUpdate** — <https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/batchUpdate>
- Docs how‑to: **InsertTextRequest** — <https://developers.google.com/workspace/docs/api/how-tos/move-text>
- YouTube Data API: **search.list** cost 100 units — <https://developers.google.com/youtube/v3/docs/search/list>
- YouTube Data API: **quota calculator** — <https://developers.google.com/youtube/v3/determine_quota_cost>

---

## 1) Scope, inputs, outputs

**Goal:** Given `{email, cvDocId, jobDescription? | jobDescriptionUrl?}`, analyze JD, score CV, find & rank tutorials per missing hard skill, propose two MVP projects, email a review link, wait for approval, batch‑update CV doc, re‑score, and email result.

**Key invariants**
- All LLM calls return **strict JSON** matching schemas; no prose leakage. Use **Structured Outputs / JSON mode**.
- CV text is obtained via Drive **`files.export`** (10 MB cap).
- Docs edits use **`documents.batchUpdate`** with `InsertTextRequest`.
- YouTube quota guarded: `search.list` is expensive (100 units), `videos.list` is cheap (1 unit). Cache queries.

**Front‑end hook**  
Repoint your `submit-cv.html` form action to the new `POST /v1/analyses`. Keep payload keys as is.

---

## 2) Tech stack

- **Python** 3.11+  
- **FastAPI** (Edge API + review page)  
- **LangGraph** (fan‑out/fan‑in, typed state)  
- **OpenAI** SDK with **Structured Outputs**  
- **google‑api‑python‑client** for Drive/Docs/Gmail  
- **HTTPX** for YouTube Data API v3  
- **Jinja2** for email templating  
- **SQLite** for persistence; **Redis** for cache (optional)

---

## 3) Repository layout

```
cv-jd-orchestrator/
├─ pyproject.toml
├─ README.md
├─ .env.example
├─ Dockerfile
├─ docker-compose.yml
└─ src/
   ├─ app/
   │  ├─ main.py           # FastAPI factory
   │  ├─ routes.py         # /v1/analyses, /v1/analyses/{id}, /approve
   │  ├─ schemas.py        # Pydantic request/response + LLM schemas
   │  ├─ config.py         # settings/env
   │  └─ templates/
   │     ├─ email/approval.html.j2
   │     └─ email/completion.html.j2
   ├─ orchestrator/
   │  ├─ state.py          # State model + reducers
   │  ├─ graph.py          # LangGraph wiring (map/fan‑in)
   │  └─ nodes/            # One pure function per node
   │     ├─ ingest.py
   │     ├─ drive_export.py
   │     ├─ merge_jd.py
   │     ├─ jd_analyze.py
   │     ├─ cv_score.py
   │     ├─ build_queries.py
   │     ├─ yt_branch.py
   │     ├─ collect.py
   │     ├─ email.py
   │     ├─ wait_approval.py
   │     ├─ docs_apply.py
   │     └─ recalc.py
   ├─ services/
   │  ├─ llm.py
   │  ├─ google_drive.py
   │  ├─ google_docs.py
   │  ├─ gmail.py
   │  ├─ youtube.py
   │  ├─ ranking.py
   │  ├─ cache.py
   │  ├─ storage.py
   │  └─ secrets.py
   └─ tests/
      ├─ test_graph.py
      ├─ test_ranking.py
      └─ fixtures.py
```

---

## 4) Codex Agent prompt pack

Design the **agent’s instruction set** to write code and wire components deterministically. Use contract‑first prompts. All outputs are code diffs or files with tests.

### 4.1 System prompt (global for the coding agent)

```
You are a senior software engineer generating production code.
Constraints:
- Follow the provided folder layout and file names exactly.
- For every function, include type hints, and a docstring with inputs/outputs/raises.
- All external calls use the provided official APIs and follow their docs.
- All LLM calls must use Structured Outputs / JSON mode with explicit schemas.
- Never hardcode secrets (read from settings or secrets service).
- Add unit tests and a minimal integration test per feature.
- If a step depends on an API quota or size limit, implement caching and guards.
Return only code blocks or shell commands ready to run. No commentary.
```

### 4.2 Tool prompts (LLM subtasks)

**JD Analyzer**  
- Output schema:  
  `{"companyName":[],"jobTitle":[],"hardSkills":[],"softSkills":[],"criticalRequirements":[]}`  
- Guardrails: normalization rules, caps, and “no hallucinations”.  
- Use **Structured Outputs**.

**CV Scorer**  
- Rubric with weights and hard‑gate on critical requirements.  
- Output schema:  
  `{"overallScore":0,"hardSkillsScore":0,"softSkillsScore":0,"matchedHardSkills":[],"matchedSoftSkills":[],"missingHardSkills":[],"missingSoftSkills":[],"strengths":[],"weaknesses":[]}`

**Personalizer & MVP**  
- Per‑tutorial personalization and **two** MVP combined projects with brief CV text.  
- Strict JSON schemas only.

---

## 5) Plan → Steps → Tasks

Each step lists what the agent should generate, how to test, and how to backtrack.

### Step A — Bootstrap project

**Tasks**
1. Create `pyproject.toml` with dependencies: `fastapi`, `uvicorn`, `pydantic`, `httpx`, `jinja2`, `langgraph`, `langchain-openai`, `google-api-python-client`, `google-auth`, `python-dotenv`, `pytest`, `pytest-asyncio`.
2. Add `.env.example` keys: `OPENAI_API_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `YT_API_KEY`, `GMAIL_SENDER`, `APP_BASE_URL`, `DB_URL`.
3. Implement `src/app/config.py` `Settings` loader.
4. Add `Dockerfile` + `docker-compose.yml`.

**Test**
- `pip install -e .` installs cleanly.
- `pytest -q` shows 0 tests collected (initially) and no import errors.

**Backtrack**
- If dependency conflicts occur, pin minimal versions and re‑lock.

---

### Step B — Edge API

**Tasks**
1. `src/app/schemas.py`: Pydantic models for:
   - `StartAnalysisRequest`, `StartAnalysisResponse`
   - `AnalysisStatusResponse`, `ApprovalResponse`
   - LLM models: `RequiredSchema`, `CVScoreSchema`, `PersonalizedProject`, `MVPProject`
2. `src/app/main.py`: app factory and Jinja2 environment.
3. `src/app/routes.py`:
   - `POST /v1/analyses` → validate body, generate `analysisId`, persist status=queued, spawn graph run.
   - `GET /v1/analyses/{id}` → read status and scores.
   - `POST /v1/analyses/{id}/approve` → flag approval and signal graph.
   - `GET /review/{id}` → simple HTML page with Approve button.

**Test**
- Unit tests for request validation and happy‑path responses.
- Start server and POST sample payload; expect `{analysisId}`.

**Backtrack**
- If async background run is tricky, return `{analysisId}` then run graph inline for now.

---

### Step C — Service wrappers (APIs)

**C.1 Drive export** — `services/google_drive.py`
```python
def export_doc_text(doc_id: str, mime: str = "text/plain") -> str:
    """
    Use Drive files.export to fetch Google Docs as text (10 MB limit).
    Returns plaintext. Raises on non-2xx.
    """
```

**C.2 Docs batch update** — `services/google_docs.py`
```python
def batch_update(doc_id: str, requests: list[dict]) -> dict:
    """
    Calls documents.batchUpdate with given request list (e.g., InsertTextRequest).
    Returns API response dict.
    """
```

**C.3 Gmail send** — `services/gmail.py`
```python
def send_html(to: str, subject: str, html: str) -> str:
    """
    Sends HTML email via Gmail API users.messages.send.
    Returns message id.
    """
```

**C.4 YouTube** — `services/youtube.py`
```python
async def search(query: str, max_results: int = 15) -> dict:
    """Call search.list (quota 100 units). Cache by normalized query."""

async def videos(ids: list[str]) -> dict:
    """Call videos.list(part=statistics,contentDetails). Cost 1 unit."""
```

**C.5 Ranking** — `services/ranking.py`
```python
def rank(skill: str, search_items: list[dict], stats_items: list[dict]) -> list[dict]:
    """
    Deterministic ranking with:
    - duration filter (>= 15 min)
    - Wilson lower bound on likes
    - Bayesian shrinkage on like rate
    - recency decay (mild > 3y)
    - engagement velocity
    - channel boosts
    - keyword boosts ("end to end","from scratch","project","full course","hands-on")
    Returns top candidates with score and metadata.
    """
```

**Test**
- Unit tests for Drive export error handling; Docs insert at index 1; YouTube caching; ranking determinism.

**Backtrack**
- If Gmail OAuth complexity slows progress, temporarily log emails to file and add Gmail later.

---

### Step D — LLM service

`services/llm.py` with **Structured Outputs** for all tasks.

```python
def jd_analyze(jd_text: str) -> RequiredSchema: ...
def cv_score(cv_text: str, jd_text: str, required: RequiredSchema) -> CVScoreSchema: ...
def personalize(skill: str, top3: list, cv_text: str, jd_text: str) -> list[PersonalizedProject]: ...
def mvp_pick(skills: list[str], tutorials: list, cv_text: str, jd_text: str) -> list[MVPProject]: ...
def recalculate(cv_text: str) -> CVScoreSchema: ...
```

**Prompt essentials**
- **System**: role, constraints, no hallucination, normalization rules, rubric math.
- **Contract**: exact JSON schema, max sizes, disallow extra keys.
- **Validation**: if schema fails, retry once with explicit error hint.

**Test**
- Golden‑file tests with fixed prompts → snapshot strict JSON.  
- Fuzz JD snippets (EN/DE) to verify schema stability.

**Backtrack**
- If JSON drift occurs, switch to function/tool‑calling wrapper that validates types before returning.

---

### Step E — Orchestrator graph

**State model** — `orchestrator/state.py`  
Fields: `analysis_id, user_email, cv_doc_id, cv_text, jd_text, required, score, missing_hard, per_skill, mvp_projects, email_html, approved`.

**Graph wiring** — `orchestrator/graph.py`  
- Nodes: `ingest → drive_export → merge_jd → jd_analyze → cv_score → build_queries → yt_map(skill branch) → collect → email → wait_approval → docs_apply → recalc → end`.

**Parallel fan‑out/fan‑in**  
Use **map** over `missing_hard` to run YouTube search → videos → rank → personalize concurrently, then a barrier/collector to merge results before email.

**Test**
- Integration test runs the compiled graph with mocks for external services and asserts:
  - Map produced N branches = `len(missing_hard)`.
  - Collect merged per‑skill payloads and built email HTML.
  - Approval flag resumes and applies Docs updates at index 1.

**Backtrack**
- If async synchronization is hard, reduce parallelism to a fixed `max_concurrency` and use a simpler barrier.

---

### Step F — Review + apply

- Email template `approval.html.j2` includes a signed link to `/review/{analysisId}` with Approve button calling `POST /v1/analyses/{id}/approve`.  
- `wait_approval` polls the flag or awaits a callback token.

**Docs apply** uses **`documents.batchUpdate`** with `InsertTextRequest` at index **1**.

**Test**
- Clickthrough simulation: set `approved=True` and confirm graph resumes, re‑scores, and emails completion.

---

## 6) Detailed function list (inputs/outputs)

### `services/google_drive.export_doc_text`
- **Input:** `doc_id`, `mime='text/plain'`  
- **Do:** call Drive **`files.export`**; if size >10 MB, raise; normalize newlines  
- **Output:** `str` CV text

### `services/google_docs.batch_update`
- **Input:** `doc_id`, `requests` (official request dicts)  
- **Do:** POST to **`documents.batchUpdate`**; use **InsertTextRequest** to add content; pass through replies  
- **Output:** API response dict

### `services/youtube.search`
- **Input:** query, `max_results` (≤15)  
- **Do:** GET `search.list` with `part=snippet&type=video&order=relevance`; cache by normalized query  
- **Output:** raw JSON

### `services/youtube.videos`
- **Input:** list of video IDs  
- **Do:** GET `videos.list(part=statistics,contentDetails)`  
- **Output:** raw JSON

### `services/ranking.rank`
- **Input:** `skill`, `search_items`, `stats_items`  
- **Do:** Merge by ID; filter duration `<15m`; compute score with Wilson + shrinkage + decay + boosts; sort desc  
- **Output:** ranked list

### `orchestrator/nodes/*`
- Each node: pure function `(state) -> state` or map‑item function `(item, state) -> item_state`. Network calls happen via `services/*` only.

### `services/llm.*`
- Each method wraps one prompt and validates JSON via Pydantic schema; on failure, one retry with direct JSON schema hint.

---

## 7) Front‑end: update your HTML

In your `submit-cv.html`, set:
```js
const WEBHOOK_URL = 'https://<your-domain>/v1/analyses';
```
Send body:
```js
{ userEmail, cvDocId, jobDescription, jobDescriptionUrl }
```
Do not expose API keys in HTML.

---

## 8) Security and quotas

- Never keep API keys in client HTML; store in server env/secret store.  
- Google OAuth scopes: least privilege for Drive export, Docs edit, Gmail send.  
- YouTube: budget `search.list` calls, cache aggressively; prefer `videos.list` expansions afterward.

---

## 9) Testing matrix

| Layer | Test | What to assert |
|---|---|---|
| Services | Drive export | 404/403 handled; ≤10 MB; UTF‑8 decode |
| Services | Docs update | Insert at index 1; replies order matches requests |
| Services | YouTube | Cache hits; budget guard; empty results path |
| LLM | JD Analyzer | Schema correctness; de‑dupe normalization; cap sizes |
| LLM | CV Scorer | Rubric math; hard‑gate when any critical missing |
| LLM | Personalizer | One item per tutorial; distinct tips; DE/EN match |
| Graph | Map/fan‑in | All branches complete; merged state deterministic |
| E2E | Happy path | Emails generated; approval resumes; Docs updated; completion email sent |

---

## 10) Backtracking and improvement loops

- **Schema drift**: switch to function/tool‑calling that returns typed objects; add server‑side JSON Schema validation before accepting LLM output.  
- **Parallel race**: add a deferred barrier node to explicitly gate fan‑in after all branches done.  
- **YouTube quota overrun**: reduce fan‑out concurrency, raise cache TTL, skip repeated queries, or pre‑rank by channel/keywords before `videos.list`.  
- **Docs API index errors**: insert at index 1; batch operations atomically.

---

## 11) Code references (snippets)

### 11.1 Drive export (official pattern)
```python
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

def export_doc_text(doc_id: str, creds: Credentials) -> str:
    service = build("drive", "v3", credentials=creds)
    data = service.files().export(fileId=doc_id, mimeType="text/plain").execute()
    return data.decode("utf-8", errors="replace")
```

### 11.2 Docs insert text (official semantics)
```python
from googleapiclient.discovery import build

def insert_text(doc_id: str, text: str, creds: Credentials):
    docs = build("docs", "v1", credentials=creds)
    req = {"requests":[{"insertText":{"location":{"index":1},"text":text}}]}
    return docs.documents().batchUpdate(documentId=doc_id, body=req).execute()
```

### 11.3 YouTube quota‑aware calls
```python
import httpx

YT_BASE = "https://www.googleapis.com/youtube/v3"

async def yt_search(api_key: str, q: str, max_results: int = 15):
    params = {"part":"snippet","q":q,"type":"video","order":"relevance",
              "maxResults":max_results,"key":api_key}
    async with httpx.AsyncClient(timeout=20) as c:
        return (await c.get(f"{YT_BASE}/search", params=params)).json()

async def yt_videos(api_key: str, ids: list[str]):
    params = {"part":"statistics,contentDetails","id":",".join(ids),"key":api_key}
    async with httpx.AsyncClient(timeout=20) as c:
        return (await c.get(f"{YT_BASE}/videos", params=params)).json()
```

### 11.4 LangGraph wiring (map + barrier)
```python
from langgraph.graph import StateGraph, END
from orchestrator.state import State
from orchestrator.nodes import (ingest, drive_export, merge_jd, jd_analyze,
                                cv_score, build_queries, yt_branch, collect,
                                email, wait_approval, docs_apply, recalc)

g = StateGraph(State)
for name, fn in [
  ("ingest", ingest), ("drive_export", drive_export), ("merge_jd", merge_jd),
  ("jd_analyze", jd_analyze), ("cv_score", cv_score), ("build_queries", build_queries),
  ("collect", collect), ("email", email), ("wait_approval", wait_approval),
  ("docs_apply", docs_apply), ("recalc", recalc)
]:
    g.add_node(name, fn)

g.add_edge("ingest","drive_export")
g.add_edge("drive_export","merge_jd")
g.add_edge("merge_jd","jd_analyze")
g.add_edge("jd_analyze","cv_score")
g.add_edge("cv_score","build_queries")

# Fan-out/fan-in over missing hard skills
g.add_node("yt_branch", yt_branch)
g.add_map("skills_map", "yt_branch", "collect")

g.add_edge("build_queries","skills_map")
g.add_edge("collect","email")
g.add_edge("email","wait_approval")
g.add_edge("wait_approval","docs_apply")
g.add_edge("docs_apply","recalc")
g.add_edge("recalc", END)

graph = g.compile()
```

### 11.5 OpenAI Structured Outputs (enforce strict JSON)
Use the Structured Outputs guide to emit typed JSON reliably and validate server‑side.

---

## 12) CI, logging, and observability

- Log every node start/end + durations + tool call counts.  
- Add “quota used” metrics for YouTube.  
- Add a replay fixture: capture one full successful run in `tests/fixtures` and allow complete replay with network off.

---

## 13) Migration notes from n8n

- The n8n graph maps one‑to‑one: Webhook → Drive export → JD Analyzer → CV Scorer → Prepare skill searches → YouTube branch (search → videos → rank → personalize) → Aggregate → Send approval email → Review webhook → Docs apply → Recalculate → Send completion email.  
- Replace any hardcoded keys with `secrets.get()`; never keep keys in HTML.

---

## 14) Runbook (local)

```bash
# 1) env
cp .env.example .env
# fill keys

# 2) install
pip install -e .

# 3) start API
uvicorn src.app.main:create_app --factory --reload

# 4) start a run
curl -X POST http://localhost:8001/v1/analyses \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","cvDocId":"<doc>","jobDescription":"..."}'
```

---

## 15) Acceptance checklist

- [ ] `/v1/analyses` returns `analysisId`.  
- [ ] Email “Analysis Ready” contains review link and structured tables.  
- [ ] Approval link resumes graph and inserts text at Docs index 1.  
- [ ] Final email shows new score and links to CV + report.  
- [ ] YouTube quota respected with cache hits.  
- [ ] All LLM outputs validate against schemas with ≤1 retry.

---

## 16) Known pitfalls

- Docs API uses `batchUpdate`; content is inserted via `InsertTextRequest` at index 1.  
- Drive export is capped at 10 MB; segment large docs or warn.  
- `search.list` is the main YouTube quota sink; cache and dedupe queries.  
- Parallel fan‑in requires an explicit barrier; rely on LangGraph’s merge/deferred pattern.

---

## 17) Next actions

1. Create the repo with the structure above.  
2. Replace the webhook URL in your `submit-cv.html` to call `/v1/analyses`.  
3. Implement **services** first, then **nodes**, then **graph**.  
4. Run unit tests, then a mocked end‑to‑end, then a live dry‑run.
