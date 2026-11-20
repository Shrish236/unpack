# Server design

Status: **design (latest).** The server is built except for the reasoning step (Gemini calls and session parsing), which is a placeholder. Built and missing parts are listed in [status.md](status.md). Where this document and the buildathon plan disagree, this document wins.

The server receives pushes from the CLI hook, analyses them (graph, session, LLM), **tracks the branch until a pull request exists**, posts and updates **one comment per PR**, renders the graph image, and serves the live graph page behind GitHub login.

Builds on [session-pipeline.md](session-pipeline.md) (what the hook sends and how a push becomes reasons), [cli-hook.md](cli-hook.md) and [ui-design.md](ui-design.md). The code graph library is described in [graph-design.md](graph-design.md).


> **Endpoint reference:** every endpoint, its request body, format and sample is in [`api-contract.md`](api-contract.md). Where that document and this one differ, `api-contract.md` describes the current build.
>
> **Revised decisions (poller replaces webhooks), supersede the sections they name.**
> - **No webhooks.** `/github/webhook`, `GITHUB_WEBHOOK_SECRET` and `webhook_deliveries` are removed. Sections 3.2, 3.4, 5.3 and the webhook items in §11, §12 and §14 describe what was replaced.
> - **Poller.** One sweep every `RECONCILE_INTERVAL_SECONDS` (default 10) covers every active tracked branch. Per repository it makes one conditional call `GET /repos/{o}/{r}/pulls` (ETag). A 304 costs no rate-limit budget, and the stored list is used. Compare results are cached on the pull request (`compare_cache`).
> - **Installations** are synced every `INSTALLATION_SYNC_SECONDS` (default 900) from `GET /app/installations`, instead of installation webhooks.
> - **Hold for a PR:** `PR_WAIT_DAYS` (default 3). After that the branch is `abandoned` and nothing is posted until the on-demand trigger, which is not built yet.
> - **One comment per PR,** updated in place. With `PR_DESCRIPTION_SECTION=true` (default) the same content is also written at the top of the PR description, between `<!-- unpack:begin -->` and `<!-- unpack:end -->`. The author's text outside those markers is never changed.
> - **Per-branch timing is gone.** `tracked_branches.next_check_at` and `POST /admin/tracked-branches/{id}/check-now` are removed. `needs_publish` means a post is outstanding.

## Contents

1. [Architecture](#1-architecture)
2. [How the server relates to the frontend](#2-how-the-server-relates-to-the-frontend-no-separate-node-server)
3. [Linking pushes to PRs](#3-linking-pushes-to-prs-track-the-branch-reconcile-on-a-timer)
4. [Data model](#4-data-model-postgres)
5. [API reference](#5-api-reference)
6. [Jobs and the worker](#6-jobs-and-the-worker)
7. [Gemini API (LLM calls)](#7-gemini-api-llm-calls)
8. [GitHub App and the PR comment](#8-github-app-and-the-pr-comment)
9. [Rendering the image](#9-rendering-the-image-must-never-be-wrong)
10. [Every case and what happens](#10-every-case-and-what-happens)
11. [Security](#11-security)
12. [Configuration](#12-configuration-env)
13. [Code layout](#13-code-layout)
14. [Running it](#14-running-it)
15. [End-to-end timeline](#15-end-to-end-timeline-typical)
16. [Build order](#16-build-order-server)
17. [Decisions and deviations](#17-decisions-and-deviations)

## 1. Architecture

```
Developer machine                 Unpack server (one machine, docker compose)
-----------------                 ---------------------------------------------------------
pre-push hook ──► /v1/ingest ───► API process (FastAPI)          Worker process (same codebase)
                                  writes rows, enqueues jobs     ├ analyze_push
GitHub ──────────► /github/webhook (optional nudge)              ├ render_image
                                  /auth/*                        ├ publish_comment
Reviewer browser ─► /a/* (static React app), /api/* (JSON)       └ reconciler (every 30 s)
                    /img/*, /render/*
                                   │               │              │
                       ┌───────────▼──┐  ┌─────────▼───┐  ┌───────▼──────┐
                       │ Postgres 16  │  │ /data files │  │ Gemini API   │
                       │ state + jobs │  │ payloads,   │  │ GitHub API   │
                       └──────────────┘  │ graphs, PNG │  │ Chromium     │
                                         └─────────────┘  └──────────────┘

cloudflared tunnel → https://unpack.<domain>
```

**Two processes, one Python codebase:**

- **API:** answers HTTP quickly. Never calls Gemini, never renders, never waits on GitHub. Stores rows and enqueues jobs.
- **Worker:** runs jobs and the reconciler loop, with retries.

**External services:**

| Service | Used for | Auth |
|---|---|---|
| Postgres 16 | all state and the job queue | password |
| Gemini API | reasons and session review | `GEMINI_API_KEY` |
| GitHub REST API | clone the repository, find PRs, create and edit the comment, check a viewer's repository access | GitHub App (JWT, then installation token); viewer's OAuth token |
| Chromium via Playwright | screenshot the graph page for the comment image | local |
| cloudflared (or ngrok) | public HTTPS URL for the comment image and live links, and optional webhooks | tunnel token |

**Neo4j** appears in the original design but is not in the current `docker-compose.yml`, and the server does not use it. See [§17](#17-decisions-and-deviations) (D1).

A public URL is needed even for a local demo: GitHub's image proxy (camo) fetches the comment image from the server, and reviewers click the live link.

## 2. How the server relates to the frontend (no separate Node server)

The graph UI is designed separately ([ui-design.md](ui-design.md)). From the server's side:

- The UI (React and Vite; React Flow for the PR view, Sigma.js for the codebase map) is built to static files in `web/dist/`. **FastAPI serves them** at `/a/{public_id}` from the same origin as the API. There is **no Node server in production**; Node is used only at build time. Same origin means no CORS, and the login cookie just works.
- The graph is **drawn in the viewer's browser**. The server's job is to return correct JSON from `GET /api/analyses/{public_id}` (contract in [§5.5](#55-live-graph)). That JSON is the whole interface between server and UI.
- In development, the UI can run Vite's dev server with a proxy to FastAPI. The server needs nothing special for it.
- The **comment image** is produced by the worker opening the same page in headless Chromium ([§9](#9-rendering-the-image-must-never-be-wrong)). The server only needs the UI to honour two things: a static mode (`?static=1`), and a `data-ready` or `data-error` signal on `<body>` when drawing finishes or fails.

The server **provides data**; the browser **draws** it.

### 2.1 Building the UI in parallel (the contract)

The UI and the server are built at the same time and joined at the end. The interface is fixed first:

1. **Pydantic models are the single source of truth** for every `/api/*` response (`app/schemas/api.py`).
2. `make contract` exports them to **JSON Schema** in `contract/schema/*.json` and writes **fixtures** to `contract/fixtures/` (a full analysis of the demo scenario, a running analysis, a failed one, node details, a map of httpx).
3. The UI generates its TypeScript types from those schemas (`json-schema-to-typescript`) and serves the fixtures with **MSW** (Mock Service Worker) during development.
4. **Contract tests on both sides:** the server's tests validate real responses against the schemas; the UI's tests load every fixture through the generated types.
5. **Joining:** turn off MSW, point the dev proxy at the real server, run the demo scenario end to end, then `npm run build`; the server image copies `web/dist`.

Any change to the contract is made in the Pydantic models first, then `make contract`, then both sides update.

## 3. Linking pushes to PRs: track the branch, reconcile on a timer

The hook runs before the push reaches GitHub, and the PR may be opened later, or never. So the server does not need the PR at ingest. It stores **the remote, the branch and the commit**, and a reconciler keeps checking until the PR exists and its comment is up to date.

### 3.1 What is tracked

On every ingest, upsert a `tracked_branches` row for `(repo, branch)`:

- `latest_head_sha` = this push's `head_sha` (set at **ingest**, so an older analysis that finishes late can never overwrite a newer push);
- `latest_push_id`;
- `status = waiting_for_pr` (unless already linked; `closed_recently` and `abandoned` go back to `waiting_for_pr`);
- **`needs_publish = true`** (reset on every new push, so the comment is updated again);
- `next_check_at = now()`.

Every push to the same remote branch flips the flag back, and the reconciler picks the branch up and posts the new analysis on its PR or PRs. The flag is cleared only after the comment shows the branch's latest analysis (§3.5).

Pushes to the **default branch** are analysed but not tracked (no PR is expected).

### 3.2 The reconciler

Runs in the worker every `RECONCILE_INTERVAL_SECONDS` (default 30). Each tick:

```
rows = tracked_branches
       WHERE status IN ('waiting_for_pr', 'linked', 'closed_recently')
         AND next_check_at <= now()
       -- linked branches with needs_publish = false are still checked (every 2 min)
       -- to notice PR head changes, closes and reopens
       ORDER BY next_check_at LIMIT 50 FOR UPDATE SKIP LOCKED

for each row:
    analysis = analysis of latest_push
    if analysis.status in ('queued', 'running'): next_check_at = now() + 15 s; continue
    prs = GET /repos/{owner}/{repo}/pulls?head={owner}:{branch}&state=open   (ETag cached)
    if prs is empty:
        if row has a linked PR: GET /repos/{owner}/{repo}/pulls/{n} → record closed or merged
        schedule the next check by backoff (§3.4); continue
    for each open PR (a branch can have PRs to several bases):
        upsert pull_requests; row.status = 'linked'
        choose = choose_analysis(pr)              # §3.3
        if choose differs from what was last published → enqueue publish_comment(pr, choose)
    next_check_at = now() + 2 min                 # keep an eye on PR head changes
```

**Webhooks are optional.** If the GitHub App's `pull_request` webhook is configured, the handler only sets `next_check_at = now()` for that branch, so comments appear within seconds. Correctness never depends on webhooks: the reconciler alone gets everything right.

### 3.3 Which analysis goes on a PR

Compare the PR's current head (`pr.head.sha`) with the analyses for this branch:

| Case | Detected by | Action |
|---|---|---|
| PR head = `latest_head_sha`, analysis done | equal SHAs | Publish it |
| PR head **behind** `latest_head_sha` (our push is not on GitHub yet) | `GET /compare/{pr_head}...{latest}` → ahead | Wait (`next_check_at = now() + 15 s`); publish when GitHub catches up. After 10 minutes, publish the newest analysis that equals or is an ancestor of the PR head |
| PR head **ahead** (commits pushed without the hook) | `GET /compare/{latest}...{pr_head}` → ahead | Publish the latest analysis with a banner: "Covers up to `abc1234`; N newer commits were not analysed" |
| **Diverged** (force push, rebase) | compare → diverged | Do **not** publish a stale analysis as current. If a comment exists, update it to say "Out of date: the branch changed after this analysis". Wait for a new push |
| Analysis failed | status | Publish a short comment: changed functions only, "Reasons unavailable for this push" |
| No analysis for this branch at all | none | Post nothing |

### 3.4 Backoff while waiting for a PR

| Time since last push | Check every |
|---|---|
| 0–10 min | 30 s |
| 10–60 min | 2 min |
| 1–24 h | 10 min |
| 1–7 days | 1 h |
| > 7 days | stop: `status = abandoned` (a new push or webhook reactivates it) |

After a PR closes or merges: `status = closed_recently`, checked hourly for 7 days to catch a reopen or a new PR from the same branch, then `abandoned`. Comments on closed PRs are left as they are. Links never expire.

### 3.5 Publishing safely

`publish_comment(pr_id, analysis_id)`:

1. Take `pg_advisory_xact_lock(pr_id)` so two publishes for one PR never run at once.
2. Skip if `pull_requests.last_published_analysis_id == analysis_id` **and** the body hash and image are unchanged.
3. If the analysis has no finished render yet, publish without the image; `render_image` re-enqueues the publish when it is done.
4. Create or update the comment (§8.3); store `comment_id`, `last_published_analysis_id` and `last_body_hash`.
5. If the published analysis is the branch's `latest_head_sha` analysis **with its image** (or rendering failed for good) on **every** open PR of the branch, set `tracked_branches.needs_publish = false`. Otherwise leave it `true` so the next tick finishes the job.

`dedupe_key = 'publish:pr:{pr_id}'` collapses bursts into one job.

## 4. Data model (Postgres)

The tables below are the design. The implemented models are in `server/app/models.py`, with a baseline migration in `server/migrations/versions/`.

| Table | Key columns and rules |
|---|---|
| `repos` | `id`, `owner`, `name`, `default_branch`, `installation_id` (NULL = App not installed), `ingest_token_hash` (SHA-256 of the token the hook sends), `graph_built_sha`, `status` (`active` / `app_missing` / `disabled`), `created_at`; unique `(owner, name)` |
| `pushes` | `id`, `repo_id`, `branch`, `base_sha`, `head_sha`, `payload_path` (gzipped payload on `/data/payloads`), `has_session`, `redaction_counts` (jsonb), `cli_version`, `received_at`; unique `(repo_id, head_sha)`. Also needs the commit list and commit messages (for the commit picker) |
| `analyses` | `id`, `push_id` (unique), `public_id` (22-character URL-safe random, unique), `status` (`queued` / `running` / `done` / `failed`), `error_code`, `error_message`, `summary`, `stats` (jsonb), `facts` (jsonb), `graph_view` (jsonb, validated, §5.5), `llm_raw` (jsonb), `llm_model`, `prompt_version`, `rejected_count`, `started_at`, `finished_at`. Needs `created_at` |
| `sessions` | `id`, `push_id` (unique), `agent`, `file_name`, `turns` (jsonb) |
| `function_reasons` | `analysis_id`, `node_id`, `reason`, `driver`, `history`, `confidence`, `evidence` (jsonb), `source`; primary key `(analysis_id, node_id)` |
| `review_findings` | `id`, `analysis_id`, `kind`, `finding`, `functions` (text[]), `evidence` (jsonb) |
| `tracked_branches` | `id`, `repo_id`, `branch`, `latest_push_id`, `latest_head_sha`, `status` (`waiting_for_pr` / `linked` / `closed_recently` / `abandoned`), `needs_publish` (default true), `next_check_at`, `last_checked_at`, `check_count`, `last_error`; unique `(repo_id, branch)` |
| `pull_requests` | `id`, `repo_id`, `number`, `tracked_branch_id`, `head_ref`, `head_sha`, `base_ref`, `title`, `html_url`, `state` (`open` / `closed` / `merged`), `comment_id`, `comment_url`, `last_published_analysis_id`, `last_body_hash`, `last_published_at`, `etag`, `updated_at`; unique `(repo_id, number)` |
| `pr_analyses` | `pr_id`, `analysis_id`, `linked_at`; primary key `(pr_id, analysis_id)` (the commit picker's history) |
| `renders` | `id`, `analysis_id`, `file_name` (unique), `width`, `height`, `bytes`, `status`, `error`, `created_at` |
| `jobs` | `id`, `type`, `payload` (jsonb), `status` (`queued` / `running` / `done` / `failed`), `attempts`, `max_attempts`, `run_after`, `locked_at`, `last_error`, `dedupe_key` (unique, nullable; cleared when the job finishes), `created_at` |
| `llm_calls` | `id`, `analysis_id`, `purpose` (`reasons` / `reasons_part` / `json_repair`), `model`, `attempt`, `prompt_version`, `input_tokens`, `output_tokens`, `thinking_tokens`, `latency_ms`, `status` (`ok` / `error` / `blocked` / `invalid_json` / `timeout`), `error`, `finish_reason`, `request_hash` (SHA-256 of the exact request), `response_text` (server side only), `created_at` |
| `webhook_deliveries` | `delivery_id` (primary key), `event`, `received_at` |
| `users` | `id`, `github_id` (unique), `login`, `avatar_url`, `created_at` |
| `web_sessions` | `id` (random, primary key), `user_id`, `oauth_token_encrypted`, `expires_at` |
| `access_cache` | `user_id`, `repo_id`, `allowed`, `checked_at`; primary key `(user_id, repo_id)` |
| `worker_heartbeat` | `worker_id` (primary key), `beat_at` |

**Rules.** One analysis per `(repo, head_sha)`. Reasons are never regenerated; a retry is only for analyses that failed.

## 5. API reference

### 5.0 Conventions

- JSON in and out (`Content-Type: application/json`), UTF-8, timestamps ISO 8601 UTC.
- **Error body (every endpoint):**

  ```json
  { "error": { "code": "invalid_payload", "message": "head_sha must be 40 hex characters", "details": {} } }
  ```

- Every response has `X-Request-Id` (also written to the logs).
- SHAs are 40-character lowercase hex. Branch names are URL-encoded where they appear in paths.

### 5.1 POST /v1/ingest (CLI hook)

**Headers**

| Header | Required | Value |
|---|---|---|
| `Authorization` | yes | `Bearer <repo ingest token>` |
| `Content-Type` | yes | `application/json` |
| `Content-Encoding` | yes | `gzip` |
| `Idempotency-Key` | no | the `head_sha` (default) |

**Body** (after gunzip; max 25 MB compressed, 150 MB uncompressed):

```json
{
  "schema_version": 1,
  "repo": { "remote_url": "https://github.com/owner/httpx.git", "owner": "owner", "name": "httpx", "default_branch": "master" },
  "branch": "feature/retries",
  "base_sha": "40 hex: merge base of HEAD and origin/<default branch>",
  "head_sha": "40 hex",
  "commits": [ { "sha": "40 hex", "message": "Add retries", "author_time": "2026-11-19T14:20:00Z" } ],
  "diff": "unified diff base..head (-U3), max 5 MB",
  "changed_files": [
    { "path": "httpx/_client.py", "old_path": null, "status": "M", "is_binary": false,
      "base_content": "… or null if added, binary or too large",
      "head_content": "… or null if deleted, binary or too large",
      "truncated": false }
  ],
  "session": {
    "agent": "gemini-cli", "agent_version": "0.x.y or null",
    "file_name": "session-2026-11-19T14-05-1a2b3c4d.jsonl",
    "lines": [ { "…": "one parsed JSONL record per element, trimmed and redacted" } ]
  },
  "redactions": { "env_value": 2, "github_token": 1 },
  "client": { "cli_version": "0.1.0", "os": "darwin", "hook": "pre-push" }
}
```

| Field | Rules |
|---|---|
| `schema_version` | must be 1 |
| `repo.owner`, `repo.name` | must match the token's repository (case-insensitive) |
| `branch` | non-empty, not starting with `refs/` (the hook strips `refs/heads/`) |
| `base_sha`, `head_sha` | 40 hex; may be equal (empty diff) |
| `commits` | 0 to 500 items, oldest first |
| `changed_files[].status` | `A` added, `M` modified, `D` deleted, `R` renamed (`old_path` set) |
| `changed_files[]` contents | at most 1 MB each; larger becomes `null` with `truncated: true` |
| `session` | may be `null` (no session found) |

**Responses**

| Status | When | Body |
|---|---|---|
| 202 Accepted | new push queued | see below |
| 200 OK | same `head_sha` already received | same shape, `"deduplicated": true` |
| 400 `invalid_payload` | JSON, schema or field rule failed | error |
| 401 `invalid_token` | missing or unknown token | error |
| 403 `repo_mismatch` | payload repository ≠ token repository | error |
| 409 `repo_disabled` | repository disabled or App not installed | error (`details.install_url`) |
| 413 `payload_too_large` | over the limits | error |
| 415 `unsupported_encoding` | not gzip JSON | error |
| 422 `unsupported_schema_version` | unknown version | error (`details.supported: [1]`) |
| 429 `rate_limited` | more than 60 pushes per minute per repository | error, `Retry-After` header |
| 503 `unavailable` | database down | error; the hook prints a warning and the push continues |

```json
{
  "push_id": 812,
  "analysis": { "public_id": "q8Xr2mVb0aLk3PzT7uYe1w", "status": "queued",
                "url": "https://unpack.example/a/q8Xr2mVb0aLk3PzT7uYe1w" },
  "tracking": { "branch": "feature/retries", "status": "waiting_for_pr" },
  "deduplicated": false
}
```

**Behaviour:** validate → write the payload file → insert `pushes` and `analyses` (queued) → upsert `tracked_branches` (§3.1) → enqueue `analyze_push`. All in one transaction, except the file write, which happens first. Orphan files are cleaned daily.

### 5.2 GET /v1/pushes/{push_id} (CLI status)

**Headers:** `Authorization: Bearer <repo ingest token>` (the token must own the push).

**200:**

```json
{
  "push_id": 812, "branch": "feature/retries", "head_sha": "…",
  "received_at": "2026-11-19T14:30:02Z",
  "analysis": { "public_id": "q8Xr2mVb0aLk3PzT7uYe1w", "status": "done", "error": null,
                "url": "https://unpack.example/a/q8Xr2mVb0aLk3PzT7uYe1w" },
  "tracking": { "status": "linked", "next_check_at": "…" },
  "pull_requests": [ { "number": 12, "url": "https://github.com/owner/httpx/pull/12",
                       "comment_url": "https://github.com/owner/httpx/pull/12#issuecomment-…",
                       "published_analysis_is_this_push": true } ]
}
```

**Errors:** 401 `invalid_token`, 404 `not_found`.

### 5.3 GitHub

#### POST /github/webhook (optional nudge)

**Headers:** `X-GitHub-Event`, `X-GitHub-Delivery`, `X-Hub-Signature-256` (HMAC-SHA256 of the raw body with `GITHUB_WEBHOOK_SECRET`).

| Event and action | Effect |
|---|---|
| `pull_request` opened, reopened, synchronize, ready_for_review, edited (base changed), closed | Find `tracked_branches` by (repo, `head.ref`); set `next_check_at = now()` (reactivate if abandoned) |
| `installation` created or deleted; `installation_repositories` added or removed | Set or clear `repos.installation_id` and `repos.status` |
| `ping` | nothing |

**Responses:** 204 handled or ignored; 401 `invalid_signature`; a duplicate `X-GitHub-Delivery` gives 204 without action. Never does slow work inline.

#### GET /github/setup

GitHub redirects here after the App is installed (`?installation_id=…&setup_action=install`). It fetches the installation's repositories, updates `repos.installation_id`, and renders a simple HTML page listing them with the next step (`unpack install`).

### 5.4 Viewer login

| Endpoint | Parameters | Result |
|---|---|---|
| `GET /auth/login` | `next` (a relative path that must start with `/a/`) | 302 to `https://github.com/login/oauth/authorize?client_id=…&redirect_uri={BASE}/auth/callback&state=<signed(nonce, next)>`; sets the short-lived `unpack_oauth_state` cookie |
| `GET /auth/callback` | `code`, `state` | Verify `state` against the cookie; exchange `code` (`POST https://github.com/login/oauth/access_token`); `GET /user`; upsert `users`; create `web_sessions` (14 days); set the `unpack_session` cookie (HttpOnly; Secure; SameSite=Lax; Path=/); 302 to `next`. Errors give a 400 HTML page: "Login failed, try again" |
| `POST /auth/logout` | none | delete the session, clear the cookie, 204 |
| `GET /api/me` | cookie | 200 `{"login": "…", "avatar_url": "…"}`, or 401 `not_logged_in` |

### 5.5 Live graph

#### GET /a/{public_id}

Serves the built UI (`web/dist/index.html`) with 200 for any ID. The UI reads the ID from the URL and calls the API. The server's part of login is the API returning 401 `not_logged_in`, which the UI turns into a redirect to `/auth/login?next=/a/{public_id}`. Unknown IDs get 404 `not_found` from the API.

#### Access rule for every `/api/analyses/*` and `/api/prs/*` call

1. A valid `unpack_session` cookie, else 401 `not_logged_in`.
2. If the `access_cache` entry is fresh (under 10 minutes), use it. Otherwise call `GET https://api.github.com/repos/{owner}/{repo}` with the viewer's token: 200 → allowed; 404 or 403 → 403 `no_repo_access`; 401 (token revoked) → delete the session, 401 `not_logged_in`.

#### GET /api/analyses/{public_id}

**200 when done** (the full contract the UI and the renderer rely on):

```json
{
  "analysis": { "public_id": "q8Xr2mVb0aLk3PzT7uYe1w", "status": "done",
                "repo": { "owner": "owner", "name": "httpx" },
                "branch": "feature/retries", "base_sha": "…", "head_sha": "…", "short_sha": "a1b2c3d",
                "created_at": "…", "finished_at": "…",
                "agent": "gemini-cli", "llm_model": "…", "prompt_version": 1, "has_session": true },
  "pull_request": { "number": 12, "title": "Add retries", "url": "…", "state": "open" },
  "banner": null,
  "summary": "Adds retry-on-connect-error to Client and AsyncClient …",
  "stats": {
    "functions_changed": 6,
    "by_source": { "session": 4, "session_then_formatted": 0, "session_partial": 0, "outside_session": 1 },
    "by_change": { "added": 2, "functional": 3, "signature": 0, "text_only": 1, "deleted": 0 },
    "not_reached_by_tests": 1
  },
  "facts": {
    "last_test_run": { "turn": "T41", "command": "pytest tests/test_client.py", "exit_code": 0, "summary": "18 passed" },
    "tested_after_final_edit": true
  },
  "graph": {
    "nodes": [ { "id": "httpx/_client.py::AsyncClient._send_single_request", "label": "AsyncClient._send_single_request",
                 "name": "_send_single_request", "kind": "method", "parent": "httpx/_client.py::AsyncClient",
                 "path": "httpx/_client.py", "start_line": 1720, "end_line": 1755,
                 "signature": "async def _send_single_request(self, request: Request) -> Response",
                 "is_async": true, "is_public": false, "layer": "changed",
                 "change": { "kind": "functional", "source": "session" },
                 "test": { "label": "none", "count": 0, "shortest_path": [],
                           "nearest_tested": "httpx/_client.py::Client._send_single_request" },
                 "callers_count": 2, "callees_count": 3, "is_test": false, "has_reason": true, "finding_ids": [3] } ],
    "edges": [ { "id": "e1", "source": "httpx/_client.py::AsyncClient.send",
                 "target": "httpx/_client.py::AsyncClient._send_single_request",
                 "kind": "CALLS", "tier": "EXTRACTED", "via": null } ],
    "collapsed": [ { "id": "c1", "anchor": "httpx/_client.py::AsyncClient.send", "direction": "callers",
                     "file": "httpx/_api.py", "count": 12, "node_ids": ["httpx/_api.py::request"] } ],
    "truncated": { "nodes_omitted": 0, "edges_omitted": 0 }
  },
  "reading_order": ["httpx/_config.py::Retry.__init__", "httpx/_client.py::Client._send_single_request",
                    "httpx/_client.py::AsyncClient._send_single_request"],
  "impact": {
    "summary": { "functions": 23, "files": 6, "public_api": 4, "uncertain_paths": 2 },
    "by_node": { "httpx/_client.py::AsyncClient._send_single_request": [
                   { "id": "httpx/_client.py::AsyncClient.send", "depth": 1, "tier": "EXTRACTED", "uncertain": false } ] }
  },
  "timeline": [
    { "turn": "T1", "kind": "user_request", "ts": "…", "label": "Add retries, keep async in sync", "nodes": [] },
    { "turn": "T14", "kind": "edit", "ts": "…", "label": "_client.py", "nodes": ["httpx/_client.py::Client.send"], "reverted": true },
    { "turn": "T15", "kind": "test_run", "ts": "…", "label": "pytest: 1 failed", "nodes": [], "exit_code": 1 },
    { "turn": "T22", "kind": "edit", "ts": "…", "label": "_client.py",
      "nodes": ["httpx/_client.py::Client._send_single_request", "httpx/_client.py::AsyncClient._send_single_request"],
      "reverted": false },
    { "turn": "T45", "kind": "claim", "ts": "…", "label": "Claims tests cover both clients", "nodes": [], "finding_id": 3 }
  ],
  "reasons": {
    "httpx/_client.py::AsyncClient._send_single_request": {
      "reason": "Mirrors the sync retry so both clients behave the same, as the user asked.",
      "driver": "user_asked", "history": "Added after the sync version passed its tests (T38).",
      "confidence": "high", "source": "session",
      "evidence": [ { "turn": "T1", "quote": "keep the async client in sync" } ] } },
  "findings": [
    { "id": 3, "kind": "claim_not_backed",
      "finding": "Agent said tests cover both clients; no test reaches AsyncClient._send_single_request.",
      "functions": ["httpx/_client.py::AsyncClient._send_single_request"],
      "evidence": [ { "turn": "T45", "quote": "I've added tests covering both clients" } ] } ],
  "diff_hunks": {
    "httpx/_client.py::AsyncClient._send_single_request": [ { "start_line": 1724, "end_line": 1740, "patch": "@@ … @@\n+ …" } ]
  }
}
```

**Field values:**

| Field | Values |
|---|---|
| `graph.nodes[].kind` | `file`, `class`, `function`, `method`, `test` |
| `graph.nodes[].parent` | the containing class or file node ID (null for files); every parent is itself in `nodes` |
| `graph.nodes[].layer` | `container` (file, class), `changed`, `neighbor`, `impact` (blast-radius depth ≥ 2 shown), `test`, `ghost` (deleted function) |
| `change.kind` | `added`, `functional`, `signature`, `text_only`, `deleted` (null for non-changed nodes) |
| `change.source` | `session`, `session_then_formatted`, `session_partial`, `outside_session` |
| `test.label` | `direct`, `reached`, `reached_uncertain`, `none` (null for test and container nodes) |
| `test.nearest_tested` | for `none` only: the closest function (by calls, either direction) that a test reaches, or null |
| `edges[].kind` | `CALLS`, `INHERITS`, `OVERRIDES`, `REACHES` (test → function, shortest path hops), `IMPORTS` (file → file, only between files shown) |
| `edges[].tier` | `EXTRACTED`, `INFERRED`, `AMBIGUOUS` |
| `collapsed[].direction` | `callers`, `callees`, `tests`: neighbours beyond the per-node cap, grouped by file |
| `timeline[].kind` | `user_request`, `edit`, `test_run`, `claim`, `out_of_band` (file changed outside the edit tool) |
| `impact.by_node[].depth` | 1 to 3 (callers upstream); `uncertain` = the path uses an `INFERRED` or `AMBIGUOUS` edge |
| `reading_order` | changed functions, ordered by calls from the entry point down (callers before callees; ties by file, then line); deleted functions last |
| `reasons[].driver` | `user_asked`, `agent_decided`, `not_stated` |
| `banner` | null, or `{ "kind": "partial_coverage" \| "out_of_date" \| "reasons_unavailable" \| "no_session", "message": "…" }` |

**Guarantees** (validated with Pydantic before the analysis is stored; a violation fails the analysis rather than storing bad data):

- node IDs are unique, and every edge's source and target is a node;
- every changed function in `stats` is a node with `layer: changed` or `ghost`;
- every `reasons` key and `findings[].functions` entry is a node ID;
- every evidence item has passed quote verification;
- every node's parent exists and is a container; containers have no change;
- every `reading_order`, `impact`, `timeline[].nodes` and `collapsed[].anchor` ID is a node (`impact` entries may also point at IDs inside `collapsed[].node_ids`);
- at most 15 shown neighbours per changed node (the rest go in `collapsed`); at most 200 non-container nodes and 500 edges overall. `truncated` reports what was cut. Changed nodes, their parents and their direct test path are never cut.

**Other responses:**

- **200 when not finished:** `{"analysis": {"public_id": "…", "status": "queued" | "running"}}`. Clients poll; the response carries `Retry-After: 3`.
- **200 when failed:** `{"analysis": {"public_id": "…", "status": "failed", "error_code": "llm_unavailable", "error_message": "…"}}`, plus whatever facts were computed (graph and changed functions if available).
- **Errors:** 401 `not_logged_in`, 403 `no_repo_access`, 404 `not_found`.

#### GET /api/analyses/{public_id}/turns?ids=T1,T14,T45

Evidence for the side panel. `ids`: 1 to 50 turn IDs. Unknown IDs are omitted.

```json
{ "turns": [
  { "turn_id": "T14", "kind": "edit", "ts": "…", "path": "httpx/_client.py",
    "instruction": "To retry on connection errors, in _send_single_request, wrap …",
    "text": null, "command": null, "exit_code": null,
    "excerpt": "diff of the touched functions, ≤ 4 KB" },
  { "turn_id": "T45", "kind": "assistant", "ts": "…", "text": "I've added tests covering both clients …", "excerpt": null }
] }
```

`kind` is one of `user`, `assistant`, `thought`, `edit`, `shell`, `read`, `plan`, `notice`. Errors as above, plus 400 `invalid_ids`.

#### GET /api/prs/{owner}/{repo}/{number}/analyses

The commit picker. Newest first, at most 50.

```json
{ "pull_request": { "number": 12, "title": "…", "url": "…", "state": "open" },
  "analyses": [ { "public_id": "…", "head_sha": "…", "short_sha": "a1b2c3d",
                  "commit_message": "Add retries", "created_at": "…",
                  "status": "done", "is_published": true } ] }
```

#### GET /api/analyses/{public_id}/nodes/{node_id}

Everything the detail panel shows for one node. `node_id` is URL-encoded. Works for any node in the analysis graph, including collapsed and impact lists.

```json
{
  "node": { "id": "httpx/_client.py::AsyncClient._send_single_request", "kind": "method",
            "path": "httpx/_client.py", "start_line": 1720, "end_line": 1755,
            "signature": "async def _send_single_request(self, request: Request) -> Response",
            "decorators": [], "is_async": true, "is_public": false, "doc": "first docstring line or null",
            "class": { "id": "httpx/_client.py::AsyncClient", "bases": ["BaseClient"] } },
  "change": { "kind": "functional", "source": "session" },
  "source_head": "the function's source at head_sha (≤ 400 lines, else truncated: true)",
  "diff": [ { "start_line": 1724, "end_line": 1740, "patch": "@@ … @@\n+ …" } ],
  "callers": [ { "id": "…AsyncClient.send", "tier": "EXTRACTED", "line": 1702, "in_graph": true } ],
  "callees": [ { "id": "…AsyncClient._transport_for_url", "tier": "INFERRED", "via": "self", "line": 1731, "in_graph": false } ],
  "unresolved_calls": [ { "raw": "self._hooks[name](request)", "line": 1735 } ],
  "file_imports": [ { "module": "httpx/_models.py", "names": ["Request", "Response"], "context": "runtime" } ],
  "file_imported_by": ["httpx/__init__.py", "httpx/_api.py"],
  "tests": {
    "label": "none", "count": 0, "paths": [],
    "nearest_tested": { "id": "…Client._send_single_request", "count": 41,
                        "path": ["tests/client/test_client.py::test_get", "…Client.get", "…Client.request", "…Client.send", "…Client._send_single_request"] }
  },
  "impact": [ { "id": "…AsyncClient.send", "depth": 1, "tier": "EXTRACTED", "uncertain": false } ]
}
```

`callers` and `callees` are capped at 100 each (`callers_total` and `callees_total` give the full counts). `tests.paths` holds up to 3 shortest paths. Errors: 401, 403, 404 `not_found` (unknown node).

#### GET /api/repos/{owner}/{repo}/map?sha={head_sha}

The whole-codebase map for the Sigma view. Same access rule. Served from a per-commit cache (`/data/maps/{repo_id}/{sha}.json.gz`), built on first request from the code graph. `ETag` = sha; `Cache-Control: private, max-age=86400`.

```json
{
  "repo": { "owner": "owner", "name": "httpx" },
  "map_sha": "40 hex (the commit the graph reflects; may differ from the requested sha)",
  "columns": ["id", "kind", "parent", "loc", "fan_in", "is_test"],
  "nodes": [
    ["httpx", "folder", null, 8827, 0, false],
    ["httpx/_client.py", "file", "httpx", 2010, 0, false],
    ["httpx/_client.py::AsyncClient", "class", "httpx/_client.py", 670, 3, false],
    ["httpx/_client.py::AsyncClient.send", "method", "httpx/_client.py::AsyncClient", 45, 6, false]
  ],
  "counts": { "folders": 4, "files": 23, "classes": 61, "functions": 440, "tests": 425 }
}
```

- Rows instead of objects keep it small (about 1 MB gzipped per 10,000 functions).
- No edges in this payload: the map draws edges only for a selected node (next endpoint).
- `map_sha` is the commit the graph was built from. The worker builds the head commit's graph during `analyze_push`, so for the latest analysis the two match. For an older analysis the response says which commit is shown.
- Changed and impact highlighting come from the analysis response, not from this payload, so one cached map serves every analysis on that commit.

#### GET /api/repos/{owner}/{repo}/nodes/{node_id}/edges?sha={sha}

Calls in and out of one node, for the map's hover and selection view.

```json
{ "id": "httpx/_client.py::AsyncClient.send",
  "callers": [ { "id": "…", "tier": "EXTRACTED" } ],
  "callees": [ { "id": "…", "tier": "INFERRED" } ],
  "callers_total": 6, "callees_total": 4 }
```

Capped at 200 each. Errors: 401, 403, 404.

### 5.6 Images and rendering

#### GET /img/{file_name}.png

Public. `file_name` is 32 random hex characters, new for every render (camo caches by URL). 200 `image/png` with `Cache-Control: public, max-age=31536000, immutable`; 404 otherwise. **No transcript text is ever in an image.**

#### GET /render/{public_id}?static=1&render_token=…

Internal. Serves the same built UI; `static=1` tells it to draw the image version (defined in [ui-design.md §5](ui-design.md#5-static-image-for-the-pr-comment)). `render_token` is an HMAC of the `public_id` and an expiry (60 seconds), accepted only from `127.0.0.1` or the compose network. The app fetches its data with the same token (`/api/analyses/{id}?render_token=…`), which bypasses user login for this one request type. Invalid tokens get 403.

### 5.7 Operations and admin

All `/admin/*` endpoints need `Authorization: Bearer <ADMIN_TOKEN>`.

| Endpoint | Request | Response |
|---|---|---|
| `GET /healthz` | none | 200 `{"ok": true}` |
| `GET /readyz` | none | 200 `{"postgres": "ok", "worker": "ok", "worker_heartbeat_age_s": 4}`; 503 with the failing part if any check fails. (Neo4j is not checked, since it is not in use.) |
| `POST /admin/repos` | `{"owner": "owner", "name": "httpx", "default_branch": "master"}` | 201 `{"repo_id": 1, "ingest_token": "unp_…" (shown once), "installation_id": 123}`; 409 `app_not_installed` with `details.install_url` |
| `POST /admin/repos/{id}/rotate-token` | none | 200 `{"ingest_token": "unp_…"}` |
| `POST /admin/repos/{id}/graph/rebuild` | `{"sha": "optional"}` | 202 `{"job_id": …}` |
| `GET /admin/jobs` | `?status=failed&type=analyze_push&limit=50` | 200 `{"jobs": [{"id", "type", "status", "attempts", "last_error", "created_at"}]}` |
| `POST /admin/analyses/{public_id}/retry` | none | 202; 409 `not_failed` if the analysis is not failed |
| `GET /admin/tracked-branches` | `?status=waiting_for_pr` | 200 `{"branches": [{"repo", "branch", "status", "latest_head_sha", "next_check_at", "pull_requests": […]}]}` |
| `POST /admin/tracked-branches/{id}/check-now` | none | 202 (sets `next_check_at = now()`) |

## 6. Jobs and the worker

**Claiming a job** (safe with several workers):

```sql
UPDATE jobs SET status = 'running', locked_at = now(), attempts = attempts + 1
WHERE id = (SELECT id FROM jobs WHERE status = 'queued' AND run_after <= now()
            ORDER BY run_after FOR UPDATE SKIP LOCKED LIMIT 1)
RETURNING *;
```

- **Failure:** `run_after = now() + 5 s × 2^attempts`, up to `max_attempts`, then `failed`.
- A job running for more than 10 minutes is reset to `queued` (worker crash).
- The worker writes `worker_heartbeat` every 10 seconds (for `/readyz`).

| Job | Max attempts | Steps | On success |
|---|---|---|---|
| `analyze_push` | 4 | 1. Load the payload. 2. Ensure the repository clone (`/data/repos/{owner}/{name}`) and the graph exist; update the graph from `changed_files` (fetch `head_sha` later if GitHub has it). 3. Parse the session into `sessions`. 4. Changed functions and edit links (pipeline §4.3 to §4.5). 5. LLM input, Gemini call (§7), verification (pipeline §4.6 to §4.8). 6. Build `graph_view` from the head graph (containers, neighbours capped per node with the rest in `collapsed`, test paths, `nearest_tested`). 7. Impact: upstream callers to depth 3 per changed node, with tiers. 8. Reading order: topological order of changed functions over `CALLS` (cycles broken by file, then line). 9. Timeline from the session turns and edit links. 10. Validate everything (§5.5 guarantees), then store in one transaction | enqueue `render_image`; set the branch's `next_check_at = now()` |
| `render_image` | 3 | §9 | set `next_check_at = now()` so the reconciler publishes with the image |
| `publish_comment` | 5 | §3.5, §8.3 | none |
| reconciler | (loop) | §3.2 | none |

**Partial failure inside `analyze_push`:** each step's output is saved as it completes. If Gemini fails after retries, the analysis is stored as `done` with `banner.kind = reasons_unavailable`. The facts and graph are still shown; nothing is lost.

## 7. Gemini API (LLM calls)

The only place the server calls an LLM is inside `analyze_push`, after the facts are computed (changed functions, edit links, test facts). What goes in and comes out is defined in [session-pipeline.md §4.6 to §4.8](session-pipeline.md#46-build-the-llm-input). This section covers how the server makes the call reliably.

### 7.1 Calls per analysis

| Purpose | When | Model | Typical count |
|---|---|---|---|
| `reasons` | always, if at least one changed function is not `text_only` | primary | 1 |
| `reasons_part` | input too large for one call, or output cut off | primary | 2 to 4 instead of 1 |
| `json_repair` | output fails schema parsing after one retry | repair (Flash) | rare |

Nothing else uses the LLM. Each call is logged in `llm_calls`.

### 7.2 Access

- **SDK:** `google-genai` (Python), wrapped in one module, `app/llm/client.py`. Nothing else imports the SDK.
- **Backends**, chosen by `GEMINI_BACKEND`:
  - `ai_studio` (buildathon): API key from Google AI Studio, `genai.Client(api_key=GEMINI_API_KEY)`.
  - `vertex` (self-hosted customers, in their own cloud): `genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)` with a service account (`GOOGLE_APPLICATION_CREDENTIALS`).
- **Data use:** on AI Studio's **free tier**, Google may use prompts to improve its products. Session text is customer data, so use a **paid** AI Studio key or Vertex AI.

### 7.3 Models

The design records these names as taken from the Gemini CLI source (`packages/core/src/config/models.ts`). That was not re-checked in this pass. All three are configurable. The startup check described below is not built yet, because the LLM client does not exist on `main`.

| Role | Env | Default | Why |
|---|---|---|---|
| Primary | `GEMINI_MODEL_PRIMARY` | `gemini-3.1-pro-preview` | Best reasoning over long sessions |
| Fallback | `GEMINI_MODEL_FALLBACK` | `gemini-2.5-pro` | Stable (GA) if the preview model errors or is unavailable |
| Repair | `GEMINI_MODEL_REPAIR` | `gemini-3.5-flash` | Fast and cheap; only fixes JSON shape |

- **Startup check:** `client.models.get(model=…)` for each. If one fails, log it and refuse to start (or start with a clear `/readyz` failure).
- The model actually used is stored on the analysis (`analyses.llm_model`).
- Preview models can change or be withdrawn. Before a demo, run the full pipeline on the demo session the day before and keep that stored analysis.

### 7.4 Request

```python
from google import genai
from google.genai import types

config = types.GenerateContentConfig(
    system_instruction=PROMPT_REASONS_V1,          # versioned file: app/llm/prompts/reasons_v1.md
    response_mime_type="application/json",
    response_schema=ReasonsOutput,                 # Pydantic model (session pipeline §4.7)
    max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,    # default 16384
    thinking_config=types.ThinkingConfig(...),     # model-dependent; see notes
    http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_S * 1000),
)
resp = client.models.generate_content(model=model, contents=llm_input_text, config=config)
parsed: ReasonsOutput | None = resp.parsed
```

- **Schema shape:** Gemini's structured output supports a subset of JSON Schema. Use **lists of objects with fixed fields**, not maps with dynamic keys (`functions: [{fn, reason, …}]`, not `{ "F1": … }`), no unions, and enums as plain string enums. The server converts the list into the API's reasons map afterwards.
- **Temperature and thinking:** for Gemini 3 models Google advises keeping temperature at its default, and thinking is controlled through `ThinkingConfig` (the exact field differs between the 2.5 and 3 generations). Use the defaults for the configured model, and check the current Gemini docs when pinning a model. This replaces the "temperature 0" in the session pipeline draft.
- **Function and turn IDs** in the prompt are short (`F1`, `F2`…, `T1`…) so quoting stays easy. The server maps them back to node IDs and turns.

### 7.5 Budgets and limits

| Limit | Default | Behaviour when exceeded |
|---|---|---|
| Input tokens per call | `GEMINI_MAX_INPUT_TOKENS=200000` (counted with `client.models.count_tokens` before sending) | Split functions into groups that share edits; one `reasons_part` call per group; the session excerpt per group keeps only its turns plus the user requests |
| Output tokens | 16,384 | `finish_reason = MAX_TOKENS` → split in half and retry |
| Changed functions sent | `MAX_LLM_FUNCTIONS=50` (most connected first) | Others: "Reason not generated (large change)" |
| Timeout per call | `GEMINI_TIMEOUT_S=120` | Retry (§7.6) |
| Concurrent calls (whole server) | `GEMINI_CONCURRENCY=2` (semaphore) | Wait |
| Tokens per repository per day | `GEMINI_DAILY_TOKEN_BUDGET_PER_REPO=5000000` | Analysis stored with a `reasons_unavailable` banner, reason "daily budget reached" |

Token counts from `resp.usage_metadata` are written to `llm_calls` for cost tracking.

### 7.6 Errors and retries

| Outcome | Detected by | Action |
|---|---|---|
| OK | `finish_reason == STOP` and `resp.parsed` valid | Go to verification (session pipeline §4.8) |
| Rate limited | HTTP 429 or `RESOURCE_EXHAUSTED` | Wait (the server's retry delay if given, else 10 s × 2ⁿ), up to 4 tries |
| Server error | 500, 503 or `UNAVAILABLE` | Retry 3 times with backoff, then the fallback model once |
| Timeout | client timeout | Retry once, then the fallback model |
| Output cut off | `MAX_TOKENS` | Split and retry |
| Invalid JSON or schema mismatch | `resp.parsed` is None, or a Pydantic error | Retry once with the same model; then one `json_repair` call (Flash) with the raw text and the schema |
| Blocked | `finish_reason == SAFETY`, or prompt blocked | No retry; `reasons_unavailable` |
| Bad request | 400 `INVALID_ARGUMENT` | No retry; log the request hash; if caused by size, split; else `reasons_unavailable` |
| Auth or permission | 401, 403 | No retry; mark `/readyz` unhealthy; `reasons_unavailable` |

If everything fails, the analysis is still stored as `done` with the facts and graph, `banner.kind = reasons_unavailable`, and the comment says "Reasons unavailable for this push". The admin retry endpoint can re-run only the LLM step later.

### 7.7 After the response

1. Map `F#` and `T#` back to node IDs and turns.
2. Run verification (session pipeline §4.8): every quote verbatim in its turn, facts not contradicted, unknown IDs dropped, missing functions added as `not_stated`.
3. Store `function_reasons`, `review_findings`, `analyses.summary` and `rejected_count`. Never call the LLM again for this analysis.

### 7.8 Prompts and versions

- Prompts live in `app/llm/prompts/` as files (`reasons_v1.md`, `json_repair_v1.md`). `PROMPT_VERSION` is stored on each analysis and each `llm_calls` row.
- A prompt change bumps the version; old analyses are not regenerated.
- Tests use a fake client that replays recorded responses (`tests/fixtures/llm/*.json`), so the pipeline is testable without the API. A separate `make eval` would run the real model on hand-labelled sessions and report correct, partly correct and wrong, plus rejection counts.

### 7.9 Privacy

- Only the trimmed, already-redacted session excerpt and the function diffs are sent. No secrets, no full repository.
- Raw responses are kept only in `llm_calls.response_text` (server side) and are never logged.

## 8. GitHub App and the PR comment

### 8.1 App settings

- **Permissions:** Pull requests: read and write; Contents: read; Metadata: read.
- **Events (optional):** Pull request.
- **Webhook URL:** `{BASE_URL}/github/webhook`, with a secret (or webhooks disabled; the reconciler covers it).
- **Callback URL:** `{BASE_URL}/auth/callback`. **Setup URL:** `{BASE_URL}/github/setup`.
- Keep the App ID, the private key (`.pem`), the client ID and secret, and the webhook secret.

### 8.2 Authentication

1. **App JWT** (RS256 with the private key): `iss = APP_ID`, `iat = now − 60`, `exp = now + 540`.
2. **Installation token:** `POST /app/installations/{installation_id}/access_tokens`, valid for 1 hour. Cached per installation and refreshed 5 minutes early. On 401, refresh once and retry.
3. Repository calls: `Authorization: Bearer <installation token>`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`.
4. Clone and fetch with the token passed through `GIT_ASKPASS`. It is never written into `.git/config`.
5. Rate limits: on 403 or 429 with `X-RateLimit-Remaining: 0` or `Retry-After`, delay the job until the reset. The reconciler uses ETags (`If-None-Match`; a 304 does not count against the limit).

### 8.3 Create or update the comment

```
lock PR
if pr.comment_id:
    PATCH /repos/{o}/{r}/issues/comments/{comment_id}  {"body": …}
    404 → the comment was deleted → clear comment_id and fall through
if no comment_id:
    find an existing App comment containing "<!-- unpack:v1 " (list issue comments, paginate)
    found → PATCH it
    else  → POST /repos/{o}/{r}/issues/{number}/comments  {"body": …}
store comment_id, comment_url, last_published_analysis_id, last_body_hash
```

A comment edited by a person is overwritten on the next publish, since it is a bot comment. A comment deleted by a person is recreated on the next **new analysis** only, not on every reconcile, so deleting it does not make it reappear at once.

### 8.4 Comment body

```markdown
<!-- unpack:v1 analysis=q8Xr2mVb0aLk3PzT7uYe1w -->

### 🧭 Unpack: what this change did and why

> ⚠️ Covers up to `a1b2c3d`; 2 newer commits were not analysed.   <!-- only when a banner is set -->

**Summary.** Adds retry-on-connect-error to `Client` and `AsyncClient` by wrapping
`_send_single_request`; adds a `retries` option to the transport config.

| | |
|---|---|
| Functions changed | **6** (4 by the agent, 1 outside the session, 1 formatting only) |
| ⚠️ Not reached by any test | `AsyncClient._send_single_request` |
| ⚠️ Claim not backed | Agent said tests cover both clients; only the sync client is tested |
| Tests after final edit | ✅ ran: 18 passed |

[![Graph of the changed code](https://unpack.example/img/6f2c…e1.png)](https://unpack.example/a/q8Xr2mVb0aLk3PzT7uYe1w)

**[Open the live graph →](https://unpack.example/a/q8Xr2mVb0aLk3PzT7uYe1w)** · reasons and evidence for each function (GitHub login and repository access required)

<sub>Analysis of `a1b2c3d` · Gemini CLI session · updated 2026-11-19 14:32 UTC</sub>
```

**Rules:** no transcript quotes. Flags come only from verified findings, at most 5 (then "and N more in the live graph"). The body is under 60,000 characters (GitHub's limit is 65,536). All user-derived text (function names, summary) is escaped for Markdown and HTML.

## 9. Rendering the image (must never be wrong)

1. Skip rendering when there is nothing to draw: no changed Python functions (a docs- or config-only change). The comment then says "No code functions changed" and has no image.
2. Playwright launches Chromium once per worker and reuses it. A new page is opened for each render, with a 1200 × 700 viewport, `deviceScaleFactor: 2` and `colorScheme: light`.
3. Open `/render/{public_id}?static=1&render_token=…`. Wait up to 20 seconds for `document.body.dataset.ready === "true"`. The UI sets `data-ready` **only after** the data is loaded and the graph is fully drawn, and sets `data-error="…"` instead if anything fails.
4. Fail the render on timeout, `data-error`, any console error, or a failed network request.
5. Take the screenshot to `/data/images/{32 random hex}.png`. Check that the file is under 2 MB and the image is not blank (pixel variance above a threshold). Otherwise fail.
6. On failure, retry once. Then mark `renders.status = failed`, and publish the comment **without** an image (the link still works). Never publish an image from a different analysis.
7. The image and the live view must match (same layout for the same data). This is a UI requirement, listed in [ui-design.md §5](ui-design.md#5-static-image-for-the-pr-comment).

## 10. Every case and what happens

### Ingest and push

| Case | Handling |
|---|---|
| Same `head_sha` pushed twice | 200 deduplicated, no new work |
| Two pushes in quick succession | Both analysed; `latest_head_sha` is set at ingest, so only the newest is published as current |
| Older push's analysis finishes after the newer push's | Not published as current (head ≠ `latest_head_sha`); kept in the commit picker |
| Force push or rebase | New `head_sha` → new analysis; the old analysis stays in history; the reconciler detects divergence (§3.3) |
| Push without a session | Analysis runs; all changes `outside_session`; banner `no_session` |
| Push of only non-Python files | Analysis done with zero changed functions; comment without an image |
| Push to the default branch | Analysed, not tracked |
| Branch deletion or tag push | Hook skips; server rejects branches starting with `refs/` |
| Several refs in one `git push` | Hook sends one payload per branch |
| Renamed file | `status: R` with `old_path`; functions matched across the rename |
| Deleted functions | Ghost nodes with their former callers |
| Very large diff (more than 200 changed functions) | All get facts; LLM reasons for the 50 most connected; others "Reason not generated (large change)" |
| Binary or over-1 MB files | Contents `null`, listed in the diff only |
| Base SHA unknown to the server's clone | Fetch it; if unreachable, use the payload's `base_content` |
| Session from another repository | The hook reads only this repository's chats folder; the server checks that edit paths are inside the repository and ignores others |
| Token for a different repository | 403 `repo_mismatch` |
| Database or server down | The hook prints a warning; the push succeeds; nothing is analysed (rerun with `unpack push` later) |

### Analysis

| Case | Handling |
|---|---|
| Gemini error, timeout, quota | Retry 3 times with backoff; then store the analysis with a `reasons_unavailable` banner |
| Gemini returns invalid JSON | One retry with a "return valid JSON for this schema" repair prompt; then as above |
| Gemini safety block | Treated as a failure → `reasons_unavailable` |
| Input too large for one call | Split by groups of functions that share edits; merge results |
| Quotes fail verification | Reason downgraded to `not_stated`; counted in `rejected_count` |
| Graph region violates the guarantees | Analysis failed with `error_code: invalid_graph_view` (bad data is never stored) |
| Worker crashes mid-job | Job reset after 10 minutes; steps are idempotent (upserts keyed by `analysis_id`) |

### PR and comment

| Case | Handling |
|---|---|
| PR opened before the analysis finishes | Reconciler waits for `done` (re-checks every 15 s) |
| PR never opened | Backoff up to 7 days, then abandoned |
| Several open PRs from one branch (different bases) | Comment on each |
| PR head behind, ahead or diverged | §3.3 |
| PR closed or merged | Comment left as is; branch `closed_recently` for 7 days |
| PR reopened, or a new PR from the same branch | Picked up by the reconciler; same or new comment |
| PR base changed | Comment stays; the next push's analysis uses the new merge base |
| Comment deleted by someone | Recreated on the next new analysis only |
| Comment edited by someone | Overwritten on the next publish |
| Two publishes at once | Advisory lock and marker search prevent duplicates |
| App uninstalled | Repository `app_missing`; ingest returns 409; reconciler skips it |
| Installation token expired | Refreshed automatically |
| GitHub rate limit or outage | Jobs delayed to the reset time; nothing lost |
| PR from a fork | Out of scope: documented. The branch lives in another repository and is not found by the reconciler |
| Repository renamed or transferred | GitHub returns 301; follow it and update `repos.owner` and `repos.name` |

### Live view and image

| Case | Handling |
|---|---|
| Not logged in | 401 → the app redirects to login, then back |
| Logged in, no repository access | 403 page: "You don't have access to this repository" |
| Token revoked on GitHub | Session deleted; log in again |
| Analysis still running | API returns `queued` or `running` with `Retry-After: 3` |
| Analysis failed | Facts that exist are shown with the error banner |
| Unknown `public_id` | "Not found" |
| Image link opened directly | PNG only; no data beyond the picture |
| Tunnel down when GitHub fetches the image | Image shows broken; the next publish uses a new file name, so it recovers. Keep the tunnel up during the demo |

## 11. Security

- **Ingest tokens:** `unp_` followed by 32 random bytes (base62), stored as SHA-256. One per repository; rotatable.
- **Webhooks:** HMAC verified with a constant-time comparison on the raw body, before parsing.
- **Secrets** (private key, webhook secret, Gemini key, OAuth client secret, admin token) come only from the environment or mounted files. They are never stored in the database and never logged.
- **Viewer OAuth tokens** are encrypted at rest (Fernet, `TOKEN_ENCRYPTION_KEY`).
- **Cookies:** HttpOnly; Secure; SameSite=Lax. The OAuth state is signed and single-use; `next` must be a relative `/a/…` path (no open redirect).
- **Live data** is returned only after login and a repository access check. A `public_id` alone grants nothing. `/render` accepts only a 60-second token from inside the server.
- **Transcripts** are stored server side only (already cleaned by the hook), and served only through `/api/analyses/{id}/turns`.
- **Headers:** `Content-Security-Policy: default-src 'self'; img-src 'self' https://avatars.githubusercontent.com data:` on the app; `X-Content-Type-Options: nosniff`. React Flow sets inline styles, so the style policy needs `'unsafe-inline'` for styles, and ELK may need `worker-src 'self' blob:`. Test both in the browser ([ui-design.md §6](ui-design.md#6-data-the-ui-uses-server-contract)).
- **Logs:** IDs, counts and timings only. Never payloads, tokens or session text.

## 12. Configuration (env)

```bash
UNPACK_BASE_URL=https://unpack.example          # public URL (tunnel): links, images, OAuth callback
DATABASE_URL=postgresql://unpack:…@postgres:5432/unpack

GEMINI_BACKEND=ai_studio                        # ai_studio | vertex
GEMINI_API_KEY=…                                # ai_studio (paid tier)
GCP_PROJECT=… GCP_LOCATION=… GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcp.json   # vertex only
GEMINI_MODEL_PRIMARY=gemini-3.1-pro-preview
GEMINI_MODEL_FALLBACK=gemini-2.5-pro
GEMINI_MODEL_REPAIR=gemini-3.5-flash
GEMINI_TIMEOUT_S=120 GEMINI_CONCURRENCY=2
GEMINI_MAX_INPUT_TOKENS=200000 GEMINI_MAX_OUTPUT_TOKENS=16384
GEMINI_DAILY_TOKEN_BUDGET_PER_REPO=5000000
PROMPT_VERSION=1
REASONING_ENABLED=false                         # built-in: the placeholder until the real module lands

GITHUB_API_URL=https://api.github.com           # configurable for GitHub Enterprise later
GITHUB_APP_ID=… GITHUB_APP_PRIVATE_KEY_PATH=/secrets/app.pem
GITHUB_CLIENT_ID=… GITHUB_CLIENT_SECRET=… GITHUB_WEBHOOK_SECRET=…   # webhook secret optional

SESSION_SECRET=… TOKEN_ENCRYPTION_KEY=… RENDER_TOKEN_SECRET=… ADMIN_TOKEN=…
DATA_DIR=/data
WORKER_CONCURRENCY=2
RECONCILE_INTERVAL_SECONDS=30
TRACK_MAX_DAYS=7
MAX_GRAPH_NODES=200 MAX_GRAPH_EDGES=500 MAX_NEIGHBORS_PER_NODE=15 IMPACT_DEPTH=3 MAX_LLM_FUNCTIONS=50
```

The server refuses to start if a required value is missing or weak, and it logs which one. `SESSION_SECRET`, `RENDER_TOKEN_SECRET` and `ADMIN_TOKEN` need at least 32 characters, and `TOKEN_ENCRYPTION_KEY` must be a valid Fernet key. Secrets have no committed defaults.

## 13. Code layout

The design layout, with the state of each file on `main` (`7ad132c`):

| Design path | Purpose | On main |
|---|---|---|
| `app/main.py` | FastAPI app, routers, static files from `web/dist` | yes |
| `app/config.py` | settings from env; startup validation | yes |
| `app/db.py`, `app/models.py` | SQLAlchemy; Alembic migrations | yes (`server/migrations/`) |
| `app/schemas/api.py` | Pydantic models for every response (the UI contract, §2.1) | yes |
| `app/routers/ingest.py` | `/v1/ingest`, `/v1/pushes` | yes |
| `app/routers/github_webhook.py` | `/github/webhook`, `/github/setup` | yes |
| `app/routers/auth.py` | `/auth/*`, `/api/me` | yes |
| `app/routers/live.py` | `/a/*`, `/api/analyses/*`, `/api/prs/*`, `/api/repos/*` | yes (`/a/*` is in `images.py`) |
| `app/routers/images.py` | `/img/*`, `/render/*` | yes |
| `app/routers/admin.py` | `/admin/*`, `/healthz`, `/readyz` (health is in `main.py`) | yes |
| `app/github/app_auth.py`, `client.py`, `comments.py`, `prs.py` | App JWT and token cache; REST wrapper; comment body and create-or-update; PR lookup and compare | `github/service.py` (auth and client), `comments.py`, `prs.py` |
| `app/pipeline/session_gemini.py` | JSONL → turns | **not built** (the session row is stored with empty turns) |
| `app/pipeline/changes.py` | changed functions, edit mapping, linking | partly: `changes.py` computes changes; edit mapping and linking are not built |
| `app/pipeline/llm_input.py`, `verify.py` | LLM input (§4.6) and verification (§4.8) | **not built** |
| `app/pipeline/graph.py` | graph library calls, region → GraphView | `graph_view.py` (builds the API graph from the library's `build_graph` over a `GitSource`), `analysis.py` (orchestration). The library's `region.py` is not used by the server |
| (not in design) | payload handling, repository clones, analysis orchestration | `pipeline/payload.py`, `pipeline/repos.py`, `pipeline/analysis.py` |
| `app/llm/client.py` | the only module importing `google-genai`; backends, retries, fallback | **not built** |
| `app/llm/schemas.py` | output models for `response_schema` | **not built** |
| `app/llm/prompts/` | `reasons_v1.md`, `json_repair_v1.md` | yes (text not reviewed here against §7.8) |
| `app/llm/placeholder.py` | (not in design) the reasoning stub | yes |
| `app/jobs/queue.py`, `worker.py`, `reconciler.py`, `render.py` | queue; job loop, reconciler loop, heartbeat; §3; §9 | yes, plus `handlers.py` (job handlers) and `publish.py` (§3.5) |
| `web/` | the UI; the server serves `web/dist` | stub only |
| `contract/schema/`, `contract/fixtures/` | JSON Schema from `make contract`; fixtures | 7 schemas; one fixture (`analysis_done.json`) |
| `docker-compose.yml` | api, worker, postgres, cloudflared | yes (Neo4j removed) |

Not in the design but present: `app/deps.py` (auth dependencies), `app/security.py` (tokens, signing, Fernet), `app/services.py`, `app/errors.py`.

## 14. Running it

```yaml
# docker-compose.yml (outline; pin exact image versions in production)
services:
  postgres: { image: "postgres:16.x", volumes: [pg:/var/lib/postgresql/data] }
  api:      { build: ./server, command: "uvicorn server.app.main:app --host 0.0.0.0 --port 8000",
              env_file: .env, volumes: [data:/data, ./secrets:/secrets:ro], depends_on: [postgres] }
  worker:   { build: ./server, command: "python -m server.app.jobs.worker",
              env_file: .env, volumes: [data:/data, ./secrets:/secrets:ro], depends_on: [postgres] }
  cloudflared: { image: "cloudflare/cloudflared:<version>", command: "tunnel run",
                 environment: [TUNNEL_TOKEN=…] }
```

The server image is a multi-stage Docker build: a Node stage runs `npm ci` and `npm run build`, and the Python stage copies `web/dist`. The Python stage also installs Chromium for Playwright. Node is used only at build time.

**First-time setup**

1. Start a **named** tunnel (fixed URL), and set `UNPACK_BASE_URL`.
2. Create the GitHub App ([§8.1](#81-app-settings)) with that URL, and install it on the httpx fork.
3. `docker compose up -d`, then run `alembic upgrade head`.
4. `POST /admin/repos` → ingest token → in the fork: `unpack install --server $UNPACK_BASE_URL --token unp_…`.
5. `POST /admin/repos/{id}/graph/rebuild` to pre-build the graph.
6. Test both orders: push, then open a PR; open a PR, then push again. The comment appears and updates in place.

## 15. End-to-end timeline (typical)

```
t=0 s    git push → hook → POST /v1/ingest → 202; branch tracked (waiting_for_pr)
t=1 s    worker: analyze_push (graph update, session parse, edit links)
t=3 s    push lands on GitHub; developer runs `gh pr create`
t=20 s   Gemini returns; verified; analysis done → render_image; branch next_check_at = now
t=21 s   reconciler: PR #12 found, head matches → publish_comment (image not ready → text only)
t=25 s   render done → reconciler → comment updated with the image
later    reviewer clicks the image → /a/<id> → GitHub login → access check → live graph
next     new push → new analysis → same comment edited; the commit picker lists both
```

## 16. Build order (server)

Status column: what is on `main` today.

| Step | Work | Status |
|---|---|---|
| 0 | Contract first: Pydantic models for every `/api/*` response, `make contract`, demo fixtures | Schemas and one fixture done; more fixtures missing |
| 1 | Compose stack, config validation, models and migrations, `/healthz`, `/readyz` | Done (`/readyz` checks Postgres and the worker heartbeat) |
| 2 | `/v1/ingest` with full validation, job queue and worker; `analyze_push` on fixture outputs | Done |
| 3 | GitHub App auth, `tracked_branches`, reconciler, `publish_comment` (text only). Test every row of §3.3 and §10 | Done (tests are mocked; no live GitHub App yet) |
| 4 | Real pipeline steps: session parser, changes, LLM, verification, graph, with the §5.5 validation | Changes, graph and validation done; **session parser, LLM and verification not done** |
| 5 | `/api/analyses/*` (including node details), `/api/repos/*/map` and node edges; contract tests; the UI build served at `/a/*` | Endpoints done; UI build is a stub |
| 6 | `/render`, `render_image`, `/img`; image in the comment | Done (tested with a real Chromium screenshot; see status.md) |
| 7 | Viewer login and access check | Done (can be cut for a demo with a single logged-in account) |
| 8 | Optional webhook nudge | Done |

## 17. Decisions and deviations

These are decided. Each one either changes the first design or resolves an open question in it.

| # | Topic | Decision | Reason |
|---|---|---|---|
| D1 | Graph storage | The code graph is built in-process by `unpack_graph`, pickled per commit under `DATA_DIR/graphs` and reused by the map and node endpoints. Neo4j is out of compose; `unpack_graph/neo4j_io.py` remains as an optional loader | Fewer moving parts for the demo. Re-add Neo4j when query load needs it |
| D2 | Source attribution without a session | Every change is `outside_session`, and the banner `no_session` says so | Without session parsing that is the honest answer |
| D3 | Graph API | The server uses the graph library directly. Change detection is done server-side in `pipeline/changes.py`, because the library's `detect_changes` needs the head commit in git, and the head is not on GitHub yet when a push arrives. Renames show as a deleted and an added function | Push-time analysis |
| D4 | `commit_message` | The first line of each commit message stored on the push. The hook sends the commits list for this | Commit picker |
| D5 | Graph shape | The library's `region.py` emits `GraphView` (`schemas/graphview.schema.json`), which the server does not use. `pipeline/graph_view.py` builds the API `GraphPayload` directly from the library's in-memory graph (`build_graph`) and its tiers and reachability labels | Analysis needs the head graph, which the library's git-based region does not return in the API shape. The library's `GraphView` stays for the CLI and its schema |
| D6 | When the graph view is built | During `analyze_push`, and stored. The 24-hour cache applies only to the codebase map | The PR image needs the same data at analysis time |
| D7 | `impact.summary.public_api` | The count of changed or impacted functions that are public: no leading underscore, and not in a private module | The design did not define it |
| D8 | Session format on the wire | Raw Gemini CLI JSONL. The parser produces the internal UnpackSession. Other agents' adapters produce the same type later | Gemini first; the common format is internal |
| D9 | Commit trailer | Deferred. One session per push, matched by the hook | Session pipeline §7 |
| D10 | Mermaid fallback for self-hosted | Cut | Not needed for the demo |
| D11 | Demo scope | Cut for the demo, in order: webhook nudge, Vertex backend, admin endpoints beyond token creation. Keep the reconciler's polling as the way PRs are found | Build time |
| D12 | Partial-failure banner | Use `reasons_unavailable` when the LLM step fails; the facts and graph remain | Design §6 |
| D13 | Open: `history` shape | Open. A string today; the UI wants steps. See [session-pipeline.md §4.7](session-pipeline.md#47-the-prompt-and-output-schema) and [ui-design.md §3.4](ui-design.md#34-where-the-reasoning-lives-three-levels) | Contract change, needs a decision |
| D14 | Open: rejected quotes | Open. Store in `analyses.llm_raw` or a new column | When the reasoning step is built |
| D15 | Open: CSP for React Flow and ELK | Open. Confirm in the browser | §11 |
| D16 | Open: Gemini model availability | Open. Confirm with a real call before the demo | §7.3 |
