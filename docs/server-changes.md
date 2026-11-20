# Server changes: gap analysis and proposal

Status: draft for brainstorming. Not committed.

Sources:
- Buildathon plan (Nov 19, 2026)
- Unpack server design (latest)
- Repo at `fef368c`, branch `claude/gifted-heisenberg-j9b1dk`

Not yet available: `unpack-session-pipeline.md` (design §4.3–4.8, the edit mapping, LLM input and verification rules) and `unpack-ui-design.md` (the render contract in design §9). Both are referenced by the server design but were not uploaded.

## 1. Where the repo stands

| Area | Design says | Repo has | Gap |
|---|---|---|---|
| Ingest API (§5.1) | `POST /v1/ingest` with full validation, payload file, rows, enqueue | `IngestPayload` / `IngestResponse` schemas only; no router | Build |
| Pre-push hook (`cli/hook.py`) | Sends gzipped payload with real owner/name and session | Hardcodes `owner = "owner"` and `default_branch = "main"`. Gzips the payload, then never sends it. Session lines are raw Gemini JSONL, untrimmed and unredacted. No commits, no trailer | Rewrite |
| Hook install (`cli/main.py`) | Installs a working hook | Hook runs `python -m cli`, but there is no `cli/__main__.py` | Fix |
| Worker (§6) | Job claim with `SKIP LOCKED`, retries, heartbeat, reconciler loop | 5-second sleep loop. No queue, no claim, no heartbeat | Build |
| Reconciler and GitHub (§3, §8) | App auth, PR discovery, compare, comment create/update with markers | `server/app/github/` is empty | Build |
| Pipeline (§4, pipeline doc) | Session parse, changed functions, edit links, LLM input, verify, region, impact, timeline | `server/app/pipeline/` is empty | Build |
| LLM (§7) | `google-genai` wrapper, prompts, fallback, repair, budgets, `llm_calls` logging | `server/app/llm/` is empty; prompt files do not exist | Build |
| Code graph (`unpack_graph/`) | Assumed to exist | Exists: `build_graph`, `detect_changes`, `build_region`, `update_graph`, Neo4j loader. Python only, uses stdlib `ast`. `tree-sitter` is declared in `pyproject.toml` but not imported | Adapter needed (see §3.6) |
| Data model (§4) | Listed tables and columns | Most tables exist. Missing: `pr_analyses`, `webhook_deliveries`, `analyses.created_at`, commit list and message on `pushes`, session link ID | Migration |
| Migrations (§12, first-time setup) | Alembic | `create_all()` at startup. No Alembic config | Add Alembic |
| Config (§12) | Refuse to start if a required secret is missing | All values have defaults. `TOKEN_ENCRYPTION_KEY` is a real-looking Fernet key committed in source. `ADMIN_TOKEN` and `SESSION_SECRET` have committed defaults | Fail fast, remove defaults |
| Health (§5.7) | `/readyz` checks Postgres, Neo4j, worker heartbeat | Hardcoded `"ok"` | Real checks |
| CORS (§2) | Same origin, no CORS | `allow_origins=["*"]` with `allow_credentials=True` | Remove |
| Live API (§5.4–5.6) | Auth, analyses, turns, nodes, map, edges, PR commit picker | Not present | Build |
| Images (§5.6, §9) | Playwright render, `/render`, `/img` | Not present | Build |
| Contract (§2.1) | Schemas plus fixtures for running, failed, node details, map | 7 schemas exported. One fixture (`analysis_done.json`) | More fixtures |
| Tests | Contract tests and pipeline tests with a fake LLM | 2 unit tests, passing (`unpack_graph` only) | Server tests |
| Docker | Multi-stage image that runs | `pip install -e .` runs before `server/` and `unpack_graph/` are copied. Likely fails. Not verified (needs a `docker build`) | Reorder |

## 2. Proposed build order

The design's §16 order is right. Below, each phase lists what the repo change is and what it unblocks.

**Phase 0: foundation**
- Config: fail fast on missing secrets, no committed defaults.
- Alembic baseline from the current models, plus the missing tables and columns (§3.5).
- Real `/readyz`.
- Remove the wildcard CORS.
- Fix Dockerfile ordering.

**Phase 1: ingest and queue**
- `routers/ingest.py`: bearer token check (sha256), §5.1 validation and error codes, payload file write, `pushes`/`analyses`/`tracked_branches` rows, enqueue. Also `GET /v1/pushes/{id}`.
- `jobs/queue.py`: claim with `SKIP LOCKED`, backoff, dedupe key, reset of stuck jobs.
- `jobs/worker.py`: job loop, heartbeat, reconciler tick.
- Fix the hook so it reads owner and name from the remote URL and actually POSTs.

**Phase 2: facts, no LLM**
- `pipeline/session.py`: parse the common session format (see §3.1).
- `pipeline/changes.py`: changed functions from `detect_changes`, plus edit mapping.
- `pipeline/graph.py`: adapter from the `unpack_graph` region shape to `GraphPayload`, plus impact (depth 3), reading order, and timeline.
- Validation against the §5.5 guarantees. A violation fails the analysis, never stores bad data.

**Phase 3: LLM**
- `llm/client.py`: the only module importing `google-genai`. Retries, fallback, repair, budgets, `llm_calls` logging.
- `pipeline/verify.py`: quote verification, fact checks.
- Tests use a fake client that replays recorded responses.

**Phase 4: GitHub and the comment**
- `github/app_auth.py`, `client.py`, `prs.py`, `comments.py`.
- Reconciler with every case in §3.3, backoff (§3.4), advisory lock on publish (§3.5).
- Publish text-only first, add the image later.

**Phase 5: render**
- Playwright worker, `/render` with the 60-second token, `/img`.
- Image wrapped in the comment link.

**Phase 6: live API**
- `/api/analyses/*`, `/api/prs/*`, `/api/repos/*/map`, node edges.
- `/a/*` serves `web/dist`.
- Contract tests against the schemas.

**Phase 7: cuttable for the demo**
- Viewer OAuth and access check (design §16 allows a single logged-in account).
- GitHub webhook nudge.
- Admin endpoints beyond token creation.
- Vertex backend.

## 3. Decisions to make

### 3.1 Session format: raw Gemini JSONL or the common Unpack format?
The buildathon plan says the server should only ever see one common format (messages, tool calls, file edits with line ranges, timestamps, model), with a thin adapter per agent. The server design says `session.lines` is raw Gemini JSONL and the server parses it (`pipeline/session_gemini.py`).

**Proposal:** the server accepts the common format only. The Gemini parser moves into the CLI as the first adapter. `pipeline/session_gemini.py` becomes `pipeline/session.py`. This also keeps the next adapter at a day's work.

### 3.2 Commit trailer
The buildathon plan asks for an `Unpack-Session: <id>` commit trailer. The server design does not mention it.

**Proposal:** store the session ID on the push, and store each commit (sha, message, trailer session ID). Use the trailer to choose among sessions when a branch has more than one. The demo has one session per change, so the trailer can ship after the demo.

### 3.3 When is the graph view built?
- Design: `graph_view` is built during `analyze_push` and stored.
- Buildathon: generated when the link is first opened, then cached for about 24 hours.

**Proposal:** keep the design's approach for the region and facts. The comment image needs them at analysis time, and they are small. Apply the 24-hour cache to the Sigma codebase map only, as the design already does.

### 3.4 No session
- Design: analysis runs, every change is `outside_session`, banner `no_session`.
- Buildathon: fall back to the linked ticket and PR description, and show where the reasoning came from.

**Proposal:** keep the design's banner. Add the PR description as a reasons source, with `source: "pr_description"` and `driver: not_stated` unless the text names a reason. Decide whether this is in the demo.

### 3.5 Which code does the graph see?
The graph needs the whole repo at the head commit, but the payload only has changed files, and content over 1 MB arrives as `null`.

**Proposal:**
1. Keep a clone at the default branch.
2. Overlay `head_content` for changed files.
3. If a changed file has `head_content: null` and is not deleted, fetch `head_sha` from GitHub.
4. If that also fails, mark the analysis partial with a banner.

Without this rule, a large file produces a wrong graph silently.

### 3.6 GraphView shape mismatch
`unpack_graph/region.py` outputs `{nodes: [{id, type, role, ghost, props}], edges, meta}` (see `schemas/graphview.schema.json`). The API contract (`GraphPayload`) expects `{kind, layer, path, change, test, callers_count, ...}`. Nothing converts between them.

**Proposal:** keep both shapes. Write `pipeline/graph.py` as the adapter, with tests that run the adapter over a real diff.

### 3.7 Demo scope
Buildathon goal: one path, push to PR comment to live graph, with login and access check on the live page.

**Proposal to cut for the demo:** webhook nudge, Vertex, Mermaid fallback, admin endpoints beyond token creation. Keep the reconciler's polling as the only way PRs are found.

**Open question:** keep GitHub OAuth for the live page (about a day of work), or use a single allowed account for the demo?

### 3.8 Missing documents
Upload `unpack-session-pipeline.md` (§4.3–4.8) and `unpack-ui-design.md` (§9 render contract). Phase 2 and Phase 3 cannot be specified precisely without them.

## 4. Smaller notes
- `unpack_graph.update_graph` re-resolves the whole repo on every push. Time it on httpx before the demo.
- Gemini model names in the design (`gemini-3.1-pro-preview`) are not checked here. The design itself says preview models can be withdrawn. Confirm availability with a real call before the demo.
- Config defaults for `TOKEN_ENCRYPTION_KEY`, `ADMIN_TOKEN`, `SESSION_SECRET` and `RENDER_TOKEN_SECRET` are committed. Rotate them if the repo is public.
