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
**Resolved (Gemini first):** the server parses raw Gemini CLI JSONL, as the server design (§5.1, §4.2) and the session pipeline doc (§3.5, §4.2) both say. The parser produces an internal `UnpackSession` (turns with stable IDs). Agent-neutral adapters come later and only need to produce that same type. The buildathon plan's "common format on the wire" is deferred.

### 3.2 Commit trailer
**Resolved (deferred):** the session pipeline doc (§7, "later") skips the `Unpack-Session` trailer. The demo uses one session per push, matched by the hook. Still store the commit list on the push, since the commit picker needs commit messages (see §5).

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

## 5. Findings from the session pipeline and UI design docs

Both docs were checked against the server design (latest). The server design wins on every conflict below.

**Consistent (no change needed):** the turn kinds, the `$patch`/`$rewindTo`/`$set` replay rules, the change labels (`session`, `session_then_formatted`, `session_partial`, `outside_session`), the LLM output shape (`functions`, `session_review`), the six review-finding kinds, the verification rules, the storage tables, and the API endpoints the UI reads.

**Conflicts to fix in the docs:**

| # | Where | Conflict | Resolution |
|---|---|---|---|
| 1 | Pipeline §3.5 | Posts to `{server}/ingest`, with `repo.remote` and `client.unpack_cli_version` | Use server design §5.1: `/v1/ingest`, `repo.remote_url` plus `owner`/`name`, and the design's `client` fields |
| 2 | Pipeline §4.6 vs §7 | §4.6 says split the LLM call when input is over ~200k tokens. §7 says splitting is skipped for now | Server design §7.1 keeps `reasons_part` for this. Decide whether to build it for the demo |
| 3 | Pipeline §4.7 | `temperature 0` | Server design §7.4 says use the model default for Gemini 3 and replaces the pipeline value. Use the default |
| 4 | UI §3.4 | Shows history as a vertical timeline (T14 tried, T15 failed, T22 fixed) | Server `history` is one string. Change the LLM output to a list of `{turn, text}` steps. This is a contract change, so make it in the Pydantic models first |
| 5 | UI §3.2 | Kind `module` | Server uses `file`. Use `file` in the UI |
| 6 | Server design §11 | CSP `default-src 'self'` | React Flow sets inline `style` attributes, which this blocks. ELK's web worker may need `worker-src blob:`. Use `style-src 'self' 'unsafe-inline'`, and add `worker-src 'self' blob:` if ELK uses a blob worker. Test in the browser |

**New gaps the docs expose:**
- **Fixtures.** The UI wants `analysis_running`, `analysis_failed`, `analysis_no_session`, `node_*`, `turns`, `pr_analyses`, and a real `map_httpx`. The repo has only `analysis_done.json`.
- **Test path nodes.** UI §3.6 draws test paths with intermediate nodes. The server must put every node on a test path into `graph.nodes`, or the UI cannot draw the path.
- **`impact.summary.public_api`.** Nothing defines it. Define it as changed or impacted functions that are public (no leading underscore, not in a private module).
- **Rejected quotes.** The pipeline keeps the original reason in a hidden `rejected` field for debugging. No table or column holds it. Store it in `llm_raw` or add a column.
- **Commit messages.** The commit picker needs them, and `pushes` stores no commit list. Add it (see §1).
- **Label mapping.** The graph library emits kinds `added`/`modified`/`deleted` and flags `functional`/`signature`/`text_only`. The API wants `added`/`functional`/`signature`/`text_only`/`deleted`. Map `modified` plus flags in `pipeline/changes.py`. The library already has `logic_hash`, `body_hash` and `signature_hash`, so §4.3 and §4.5 need no new hashing.
- **Session-edit mapping.** `extract_file(path, data)` takes bytes, so it can parse the session's `originalContent` and `newContent` in memory (§4.4) without a repo checkout.
- **Unverified.** The pipeline cites Gemini CLI commit `808199f` for the session format. I could not check it from here. The pipeline's own build step 1 (parse three real sessions) must confirm `resultDisplay` contains `originalContent`/`newContent` and that `replace` calls carry `instruction`.

**UI and server contract to confirm:**
- Node `kind` values: the server uses `file, class, function, method, test`.
- Change badges map from the API `change.kind`: `functional` = Modified, `signature` = Signature, `text_only` = Formatting, `added`, `deleted` = Ghost.
- The map endpoint's `folder` rows match the UI's d3-hierarchy packing.

## 6. Status: server built, reasoning left as a placeholder

Built to the server design (latest), with the Gemini and reasoning code left out:

| Area | Where | State |
|---|---|---|
| Config, fail-fast secrets | `server/app/config.py` | Required secrets have no defaults. Startup lists what is missing |
| Data model + Alembic baseline | `server/app/models.py`, `server/migrations/` | Round-trips (upgrade, downgrade, upgrade). `alembic check` shows no drift |
| Ingest (§5.1, §5.2) | `routers/ingest.py` | gzip limits, schema version, validation, repo match, app-missing 409, rate limit, dedupe, tracking |
| Job queue and worker (§6) | `jobs/queue.py`, `jobs/worker.py` | `SKIP LOCKED` claim, retries with backoff, dedupe keys, stuck-job reset, heartbeat |
| Analysis (§6, §5.5) | `pipeline/analysis.py`, `pipeline/graph_view.py` | Changed functions, neighbours, test paths, impact, reading order, diff hunks, collapsed groups, §5.5 validation |
| Reconciler (§3) | `jobs/reconciler.py` | Every §3.3 case, backoff §3.4, abandon after `TRACK_MAX_DAYS` |
| Comment (§3.5, §8) | `jobs/publish.py`, `github/comments.py` | Advisory lock, marker search, create/update/404 handling, body hash skip |
| GitHub App (§8.2) | `github/service.py`, `github/prs.py` | App JWT, installation token cache (UTC expiry), retries, rate limit |
| Render and image (§9) | `jobs/render.py`, `routers/images.py` | Chromium screenshot, data-ready and data-error contract, size and blank checks, `/render` token |
| Live API (§5.5, §5.6) | `routers/live.py` | Analysis, turns, node detail, commit picker, map with ETag, node edges |
| Viewer login and access (§5.4) | `routers/auth.py`, `deps.py` | OAuth state in a signed JWT, Fernet-encrypted tokens, 10-minute access cache |
| Webhook and setup (§5.3) | `routers/github_webhook.py` | HMAC check, delivery dedupe, installation events, setup page |
| Admin (§5.7) | `routers/admin.py` | Create repo (checks the App), rotate token, rebuild graph, jobs, retry, tracked branches |
| Health (§5.7) | `main.py` | `/readyz` checks Postgres and the worker heartbeat |

**Placeholder (reasoning, Gemini):** `server/app/llm/placeholder.py`. Returns no reasons, findings or timeline. Analyses carry the `reasons_unavailable` banner (or `no_session` when the push had no session). `REASONING_ENABLED` must stay `false` until the real module lands. Session parsing is not built: the session row is stored with empty turns.

**Deviations from the design, on purpose:**
- **Neo4j is not used.** The code graph is built in-process by `unpack_graph`, pickled per commit under `DATA_DIR/graphs`, and reused by the map and node endpoints. Neo4j was removed from `docker-compose.yml`. Re-add it when the map or query load needs it.
- **Source attribution is `outside_session` for every change.** Without session parsing that is the honest answer, and the banner says so.
- **Graph API.** The server is written against the graph stack (`graph/09-docs`). Change detection is done server-side (`pipeline/changes.py`) because the library's `detect_changes` needs the head commit in git, and the head is not on GitHub yet when a push arrives. Renames show as a deleted and an added function.
- **`commit_message` is the first line of the commit message stored on the push.** The hook needs to send commits for this to be populated.

**Verified here:**
- 49 tests pass against local Postgres 16 (`pytest tests/`). They cover config, tokens, diff parsing, ingest errors and dedupe, the analysis from a real git origin (including the case where the head is not on the origin), the reconciler cases, comment publishing and idempotence, webhook signatures, admin, OAuth login, the render route, and the served image URL.
- A real screenshot through Chromium: a 2400×1400 PNG (1200×700 at 2×), 56 KB, passes the blank check. It was rendered from `/render` on a running uvicorn.
- A bug found in that check and fixed: the comment linked `/img/<name>` but the route expects `<name>.png`, so every image would have 404'd.

**Not verified:**
- The Docker build. The Dockerfile order is fixed (sources before the editable install), but I could not run `docker build` here.
- A real GitHub App, OAuth app or webhook delivery. All GitHub calls are mocked in tests.
- The CLI hook. It still hardcodes the owner, never sends the payload and passes raw session lines. It needs its own pass before a real push reaches this server.
- The web UI. `web/src/App.tsx` fails `tsc` on an unused import (`React`). That is the UI session's code. I built the bundle with `vite build` only to test the render path.

**Still to do:**
- Fixtures for the UI: `analysis_running`, `analysis_failed`, `analysis_no_session`, node details, turns, PR analyses, and a real map.
- Reasoning and session parsing (later, Gemini first).
- Trailer linking (deferred per the pipeline doc).

**Running it:**
1. Set the env vars in `.env.example` (generate real secrets; the server refuses to start otherwise).
2. `cd server && alembic -c alembic.ini upgrade head`
3. `uvicorn server.app.main:app --port 8000` and `python -m server.app.jobs.worker`.
4. `pytest tests/` (needs a Postgres at `DATABASE_URL`, or the default test database).


## 7. Audit against the design (after merge)

Every endpoint in design §5 is served. The routes are listed in the OpenAPI schema (`/openapi.json`).

| Design section | Endpoints | State |
|---|---|---|
| §5.1 | `POST /v1/ingest` | Implemented: gzip limits, validation, repo match, dedupe, rate limit, tracking |
| §5.2 | `GET /v1/pushes/{id}` | Implemented |
| §5.3 | `POST /github/webhook`, `GET /github/setup` | Implemented: HMAC, delivery dedupe, installation events, setup page |
| §5.4 | `GET /auth/login`, `GET /auth/callback`, `POST /auth/logout`, `GET /api/me` | Implemented. Login states are now single use (`oauth_states` table) |
| §5.5 | `GET /a/{id}`, analysis, turns, node detail, PR commit picker, map, node edges | Implemented. Node detail now returns `callers_total`, `callees_total` and `unresolved_calls` |
| §5.6 | `GET /img/{file}.png`, `GET /render/{id}` | Implemented. The render route refuses non-internal clients |
| §5.7 | `/healthz`, `/readyz`, all `/admin/*` | Implemented. `/readyz` has no Neo4j check (see differences) |

**Differences from the design, and why:**

- **Neo4j is not used.** The graph lives in-process and is cached per commit as a pickle (`DATA_DIR/graphs`). Map and node reads use the same cache. Neo4j was removed from compose.
- **Graph building is incremental.** A head graph is `update_graph` on top of a cached base graph (one per base commit). The design builds whole graphs per push. The result is checked equal to a full rebuild in the tests.
- **Change detection is server-side.** The library's `detect_changes` needs the head commit in git, which GitHub may not have yet. Renames therefore show as one deleted and one added function.
- **`Idempotency-Key` is not read.** Dedupe is by `(repo, head_sha)`, which is the design's default.
- **Node `tests.paths` has one path.** The library returns the shortest path only.
- **PR list requests send no ETag.** Each reconcile tick asks GitHub afresh.
- **Content-Security-Policy adds `style-src 'self' 'unsafe-inline'` and `worker-src blob:`.** React Flow sets inline styles, and ELK may use a blob worker (see the UI findings).
- **Folder rows carry line totals** (design §5.5 example), computed from the files beneath them.

**Fixed in this pass** (found by the audit):
- `needs_publish` was never cleared. It now clears when every open PR shows the latest analysis, and the publish step recalculates it.
- A PR behind an older analysis, after 10 minutes, now gets the newest ancestor analysis (design §3.3). Before, nothing was published.
- The map and node endpoints answered with a server error for a commit the server cannot reach. They now return 404 `not_found`.
- Graph output depended on set iteration order, so a worker process could order the same edges differently. Iteration is now sorted.
- Comment images: the link now matches the route (`/img/<name>.png`).

**Performance** (SQLAlchemy, 258 files, about 11,700 functions, one changed function; `ANALYSIS_PROCESSES` controls parallelism):

| Case | Time | What runs |
|---|---|---|
| Old pipeline (full base + full head) | 20.1 s | full base build, full head build |
| Cold base, incremental head | 14.3 s | full base build (cached), incremental head |
| Warm base, incremental head | 8.1 s | base loaded from cache (1.7 s), incremental head (about 3 to 4.5 s) |

The incremental head alone takes 2.5 to 4.5 s against 8.7 s for a full build. The head-timing spread is machine noise.

**Throughput:** four warm analyses take 32.8 s run one after another. With `ANALYSIS_PROCESSES=2` they take 14.3 s, about 2.3 times the throughput. The compose worker is set to 2.

**Tests:** 131 passed, 4 skipped, run with `pytest tests/ -n auto` (about 26 s; serially about 45 s). Each xdist worker has its own database. The four skips need a launchable Chromium on this machine.

**Still not verified:**
- The Docker build. The image builds through pip. The Playwright step needs the network path that is the sandbox's, not the repo's. The web stage runs `npm ci`, which needs a lockfile that `web/` does not have, and falls back to `npm install`. Lock it on the UI side.
- A real GitHub App, OAuth app and webhook delivery. All GitHub calls are mocked.
- The CLI hook against a real push.


## 8. Container verification

Run against the image built from `server/Dockerfile` and the real `docker-compose.yml` (with an override that points the services at the built image).

**Verified:**
- The image builds: pip install of the project, the Playwright browser with its system dependencies, and the web stage. The web stage needed the sandbox CA for `npm`, which is environment-only.
- Chromium launches inside the container, and the server imports and migrations are present.
- `docker compose up`: Postgres healthy, `migrate` runs and exits 0, the API and worker start, `/healthz` and `/readyz` report the worker heartbeat.
- End to end: a repository row, a push through `POST /v1/ingest` (202), the worker clones from a git origin inside its container, and the analysis finishes with the expected facts (2 changed functions, 1 added, 1 functional, 1 not reached by tests).
- Rendering: the worker renders through the API's internal `/render` route and produces a 2400×1400 PNG, which the public `/img` route serves.
- Migrations are idempotent (re-run exits 0, stays at head).

**Found and fixed:**
- The worker rendered against `127.0.0.1:8000`, which is itself inside the worker container, so every render failed with connection refused. The compose worker now sets `INTERNAL_API_URL=http://api:8000`.

**Found, not fixed (UI side):**
- The web bundle does not build: `web/src/App.tsx` fails `tsc` on an unused import. The Dockerfile's fallback then ships an empty `index.html`, so the live page and the comment image cannot render until the UI builds. The fallback hides the failure; it should fail the build once the UI is ready.
- The API's Content-Security-Policy blocks inline scripts. That is intended (design §11): a Vite build loads only same-origin files.
- `web/` has no lockfile, so the `npm ci || npm install` fallback is not reproducible.

**Verification-only (not in the repo or the image):** the render check used a test page served from `/assets`, to exercise Chromium, the route and the image checks without the UI.
