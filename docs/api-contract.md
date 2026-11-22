# Unpack API contract

This document lists every HTTP endpoint the server exposes: its method and path, who may call it, the request format, the request body, the responses, and a sample. It describes the server on branch `claude/gifted-heisenberg-j9b1dk` (poller build). The machine-readable source is the FastAPI schema at `GET /openapi.json` on a running server, and the Pydantic models in `server/app/schemas/api.py`. If this document and the code disagree, the code is right and this document needs fixing.

Examples use `https://unpack.example.com` as the base URL. Replace it with `UNPACK_BASE_URL`.

## 1. Conventions

### 1.1 Authentication

| Caller | How it authenticates | Used by |
|---|---|---|
| CLI hook | `Authorization: Bearer unp_<43 chars>`: the repository's ingest token, issued by `POST /admin/repos` | `/v1/*` |
| Admin | `Authorization: Bearer <ADMIN_TOKEN>` (from the environment) | `/admin/*` |
| Viewer (browser) | Cookie `unpack_session`, set by `GET /auth/callback` after GitHub login. Lasts 14 days | `/api/*`, `/a/*` |
| Renderer (internal) | `render_token` query parameter, an HMAC valid for 60 seconds, plus a loopback or private-network caller | `/render/*` |
| None | Public | `/healthz`, `/readyz`, `/img/*`, `/github/setup`, `/auth/login`, `/favicon.ico` |

A viewer can only read a repository that GitHub says they can access. The server checks this with the viewer's own GitHub token and caches the answer for 10 minutes.

### 1.2 Content types and encoding

- Request bodies are JSON (`Content-Type: application/json`).
- `POST /v1/ingest` must be gzip-compressed: send `Content-Encoding: gzip`. Other encodings return `415`.
- Responses are JSON unless the table says otherwise (HTML for the setup page and the web app, PNG for images).
- Timestamps are ISO 8601 in UTC.
- SHAs are 40 lowercase hex characters.

### 1.3 Limits

| Limit | Value | Setting |
|---|---|---|
| Compressed ingest body | 25 MB | `MAX_PAYLOAD_COMPRESSED_BYTES` |
| Uncompressed ingest body | 150 MB | `MAX_PAYLOAD_UNCOMPRESSED_BYTES` |
| Diff text | 5 MB | fixed |
| One file's `base_content` or `head_content` | 1 MB | fixed |
| Commits per push | 500 | fixed |
| Pushes per repository | 60 per minute | `PUSHES_PER_MINUTE_PER_REPO` |
| Viewer access cache | 10 minutes | `ACCESS_CACHE_SECONDS` |
| Viewer session | 14 days | fixed |

### 1.4 Error format

Every error uses the same body:

```json
{
  "error": {
    "code": "not_found",
    "message": "no such analysis",
    "details": {}
  }
}
```

`details` is always present, and may be empty. Some errors add fields there (for example, `install_url`). Validation errors on any endpoint return `400` with code `invalid_payload`, and `message` names the first failing field.

| HTTP | `code` | Meaning |
|---|---|---|
| 400 | `invalid_payload` | Body or parameter is malformed, or a field is out of range |
| 400 | `invalid_next` | `next` on `/auth/login` is not a relative `/a/` path |
| 400 | `invalid_ids` | `ids` on the turns endpoint has no turn IDs, or more than 50 |
| 401 | `invalid_token` | Missing or unknown ingest token |
| 401 | `unauthorized` | Missing or wrong admin token |
| 401 | `not_logged_in` | No valid viewer session |
| 403 | `repo_mismatch` | The payload names a different repository from the token's |
| 403 | `no_repo_access` | The viewer cannot read this repository on GitHub |
| 403 | `forbidden` | Render endpoint called from outside, or with a bad or expired token |
| 404 | `not_found` | The resource does not exist, or the graph for that commit is unavailable |
| 409 | `repo_disabled` | Repository is disabled, or the GitHub App is not installed (see `details.install_url`) |
| 409 | `repo_exists` | `POST /admin/repos` for a repository already registered (`details.repo_id`) |
| 409 | `app_not_installed` | The GitHub App is not installed on that repository (`details.install_url`) |
| 409 | `not_failed` | Retry requested for an analysis that is not failed |
| 413 | `payload_too_large` | A size limit was exceeded |
| 415 | `unsupported_encoding` | Wrong `Content-Encoding` or `Content-Type`, or invalid gzip |
| 422 | `unsupported_schema_version` | `schema_version` is not `1` (`details.supported`) |
| 429 | `rate_limited` | Too many pushes in the last minute. Response has `Retry-After: 60` |
| 503 | `unavailable` | GitHub could not be reached. Retry later |
| 503 | `app_not_configured` | `GITHUB_APP_ID` is not set |
| 503 | `unavailable` | The web app is not built (`/a/*`, `/render/*`) |

## 2. Endpoint index

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/v1/ingest` | ingest token | Submit a push from the CLI hook |
| GET | `/v1/pushes/{push_id}` | ingest token | Read the state of a push the CLI sent |
| GET | `/github/setup` | none | GitHub App post-install page |
| GET | `/auth/login` | none | Start GitHub login |
| GET | `/auth/callback` | none (state checked) | Finish GitHub login |
| POST | `/auth/logout` | cookie | End the viewer session |
| GET | `/api/me` | viewer | Current user |
| GET | `/api/analyses/{public_id}` | viewer | Full analysis |
| GET | `/api/analyses/{public_id}/turns` | viewer | Session turns by ID |
| GET | `/api/analyses/{public_id}/nodes/{node_id}` | viewer | One function or class in detail |
| GET | `/api/prs/{owner}/{repo}/{number}/analyses` | viewer | Analyses linked to a pull request |
| GET | `/api/repos/{owner}/{repo}/map` | viewer | Codebase map at a commit |
| GET | `/api/repos/{owner}/{repo}/nodes/{node_id}/edges` | viewer | Callers and callees of a node |
| GET | `/img/{file_name}` | none | Rendered analysis image |
| GET | `/render/{public_id}` | internal + render token | Page the renderer screenshots |
| GET | `/a/{public_id}` | none (page loads data with the viewer's cookie) | Web app page for an analysis |
| GET | `/healthz` | none | Process is up |
| GET | `/readyz` | none | Database and worker are healthy |
| GET | `/favicon.ico` | none | Returns 204 |
| POST | `/admin/repos` | admin | Register a repository and issue its ingest token |
| POST | `/admin/repos/{repo_id}/rotate-token` | admin | Issue a new ingest token |
| POST | `/admin/repos/{repo_id}/graph/rebuild` | admin | Queue a graph rebuild |
| GET | `/admin/jobs` | admin | List queue jobs |
| POST | `/admin/analyses/{public_id}/retry` | admin | Retry a failed analysis |
| GET | `/admin/tracked-branches` | admin | List tracked branches |

There is no webhook endpoint. The server finds pull requests by polling GitHub every `RECONCILE_INTERVAL_SECONDS` (default 10). `POST /admin/tracked-branches/{id}/check-now` no longer exists.

## 3. CLI hook endpoints

### 3.1 POST /v1/ingest

Receives one push from the pre-push hook. The server stores the payload and queues an analysis.

**Auth:** `Authorization: Bearer unp_…` (the repository's ingest token).

**Request headers**

| Header | Value |
|---|---|
| `Authorization` | `Bearer unp_<token>` |
| `Content-Type` | `application/json` |
| `Content-Encoding` | `gzip` |

**Request body** (JSON before gzip)

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | integer | yes | Must be `1` |
| `repo` | object | yes | `{owner, name, remote_url?, default_branch?}`. Must match the token's repository, case-insensitively |
| `branch` | string | yes | Non-empty. Must not start with `refs/` |
| `base_sha` | string | yes | 40 lowercase hex characters |
| `head_sha` | string | yes | 40 lowercase hex characters |
| `commits` | array | no | Up to 500 items of `{sha, message, author_time}`. Each `sha` is 40 hex characters |
| `diff` | string | no | Unified diff text, up to 5 MB |
| `changed_files` | array | no | Items of `{path, old_path?, status, is_binary?, base_content?, head_content?, truncated?}`. `status` is `A`, `M`, `D` or `R`. `R` needs `old_path`. Content up to 1 MB each |
| `session` | object or null | no | `{agent, agent_version?, file_name, lines[]}`: the parsed agent session, if any |
| `redactions` | object | no | Counts of redacted secrets by kind, for example `{"api_key": 2}` |
| `client` | object | no | `{cli_version, os, hook}` |

**Responses**

| Status | When | Body |
|---|---|---|
| 202 | New push. Analysis queued | Push response (below) with `deduplicated: false` |
| 200 | Same `head_sha` already received | Push response with `deduplicated: true` and the existing analysis |

**Push response**

| Field | Type | Notes |
|---|---|---|
| `push_id` | integer | Use with `GET /v1/pushes/{push_id}` |
| `analysis.public_id` | string | 22-character ID |
| `analysis.status` | string | `queued`, `running`, `done` or `failed` |
| `analysis.url` | string | Browser link: `{UNPACK_BASE_URL}/a/{public_id}` |
| `tracking.branch` | string | The pushed branch |
| `tracking.status` | string | `untracked` (default branch or not tracked), `waiting_for_pr`, `linked`, `closed_recently` or `abandoned` |
| `deduplicated` | boolean | `true` when the head was already received |

**Sample request** (shown before gzip)

```bash
gzip -c payload.json | curl -sS -X POST https://unpack.example.com/v1/ingest \
  -H "Authorization: Bearer unp_<ingest-token>" \
  -H "Content-Type: application/json" \
  -H "Content-Encoding: gzip" \
  --data-binary @-
```

```json
{
  "schema_version": 1,
  "repo": {"owner": "acme", "name": "billing", "default_branch": "main"},
  "branch": "feat/invoice-rounding",
  "base_sha": "3f2a9c1d7e4b8a60c5d91f2e3a7b4c8d9e0f1a2b",
  "head_sha": "9b8e4d2a1c7f6e5d3b0a9c8f7e6d5c4b3a2f1e0d",
  "commits": [
    {
      "sha": "9b8e4d2a1c7f6e5d3b0a9c8f7e6d5c4b3a2f1e0d",
      "message": "Round invoice totals to cents",
      "author_time": "2026-11-20T09:14:02Z"
    }
  ],
  "diff": "diff --git a/billing/invoice.py b/billing/invoice.py\n...",
  "changed_files": [
    {
      "path": "billing/invoice.py",
      "status": "M",
      "is_binary": false,
      "base_content": null,
      "head_content": null,
      "truncated": false
    }
  ],
  "session": {
    "agent": "claude_code",
    "agent_version": "1.0.0",
    "file_name": "session-2026-11-20.jsonl",
    "lines": []
  },
  "redactions": {},
  "client": {"cli_version": "0.1.0", "os": "linux", "hook": "pre-push"}
}
```

Sample response, `202 Accepted`:

```json
{
  "push_id": 418,
  "analysis": {
    "public_id": "q7Lk2mT9xVbR4sYc8nHwFA",
    "status": "queued",
    "url": "https://unpack.example.com/a/q7Lk2mT9xVbR4sYc8nHwFA"
  },
  "tracking": {"branch": "feat/invoice-rounding", "status": "waiting_for_pr"},
  "deduplicated": false
}
```

**Errors:** `400 invalid_payload`, `401 invalid_token`, `403 repo_mismatch`, `409 repo_disabled`, `413 payload_too_large`, `415 unsupported_encoding`, `422 unsupported_schema_version`, `429 rate_limited`.

### 3.2 GET /v1/pushes/{push_id}

Returns the state of a push that the token's repository sent. The CLI can poll this after a push to show the analysis status.

**Auth:** ingest token.

**Path parameter:** `push_id` (integer).

**Response `200`**

| Field | Type | Notes |
|---|---|---|
| `push_id` | integer | |
| `branch` | string | |
| `head_sha` | string | |
| `received_at` | string | ISO 8601 |
| `analysis` | object | `{public_id, status, error, url}`. `error` is the error code, or null |
| `tracking` | object | `{status}`: `untracked`, `waiting_for_pr`, `linked`, `closed_recently` or `abandoned` |
| `pull_requests` | array | Open pull requests whose head is this branch: `{number, url, comment_url, published_analysis_is_this_push}` |

**Sample request**

```bash
curl -sS https://unpack.example.com/v1/pushes/418 \
  -H "Authorization: Bearer unp_<ingest-token>"
```

**Sample response `200`**

```json
{
  "push_id": 418,
  "branch": "feat/invoice-rounding",
  "head_sha": "9b8e4d2a1c7f6e5d3b0a9c8f7e6d5c4b3a2f1e0d",
  "received_at": "2026-11-20T09:14:58+00:00",
  "analysis": {
    "public_id": "q7Lk2mT9xVbR4sYc8nHwFA",
    "status": "done",
    "error": null,
    "url": "https://unpack.example.com/a/q7Lk2mT9xVbR4sYc8nHwFA"
  },
  "tracking": {"status": "linked"},
  "pull_requests": [
    {
      "number": 42,
      "url": "https://github.com/acme/billing/pull/42",
      "comment_url": "https://github.com/acme/billing/pull/42#issuecomment-3120457788",
      "published_analysis_is_this_push": true
    }
  ]
}
```

**Errors:** `401 invalid_token`, `404 not_found` (no such push in this repository).

## 4. GitHub App and login

### 4.1 GET /github/setup

The page GitHub sends the browser to after the App is installed. It lists the repositories the installation can access, links them to Unpack, and shows the next step. It returns HTML.

**Query parameters**

| Name | Type | Required | Notes |
|---|---|---|---|
| `installation_id` | integer | yes | From GitHub |
| `setup_action` | string | no | Passed by GitHub (for example `install` or `update`). The server does not branch on it |

**Sample request**

```bash
curl -sS "https://unpack.example.com/github/setup?installation_id=53917204&setup_action=install"
```

**Response `200`** (`text/html`). The body lists the repositories and says: "Next step: run `unpack install` in each repository to install the pre-push hook."

**Errors:** `422` if `installation_id` is missing or not an integer, `503 unavailable` if GitHub cannot be reached.

### 4.2 GET /auth/login

Starts the GitHub OAuth login. It sets a one-time state cookie and redirects to GitHub.

**Query parameters:** `next` (optional). A relative path that starts with `/a/`. Anything else returns `400 invalid_next`.

**Sample request**

```bash
curl -sS -i "https://unpack.example.com/auth/login?next=/a/q7Lk2mT9xVbR4sYc8nHwFA"
```

**Response `302`:** `Location: https://github.com/login/oauth/authorize?client_id=…&redirect_uri=https%3A%2F%2Funpack.example.com%2Fauth%2Fcallback&state=…&scope=read%3Auser+repo`, and `Set-Cookie: unpack_oauth_state=…; HttpOnly; Secure; Max-Age=600`. The `repo` scope lets the server check which repositories the viewer can read.

Each state is accepted once and expires after 10 minutes.

### 4.3 GET /auth/callback

GitHub redirects here after login. The server exchanges the code, stores the token encrypted, and creates the session.

**Query parameters:** `code`, `state` (both from GitHub).

**Response `302`** to `next` (or `/`), with `Set-Cookie: unpack_session=…; HttpOnly; Secure; Max-Age=1209600`.

On any failure (missing or reused state, bad code), the response is `400` with an HTML page that says "Login failed, try again."

### 4.4 POST /auth/logout

Ends the viewer session. It deletes the session row and clears the cookie.

**Request:** no body. Cookie `unpack_session` (optional).

**Response `204`**, no body.

## 5. Viewer endpoints

All viewer endpoints need the `unpack_session` cookie. Without it, they return `401 not_logged_in`. The browser sends the cookie automatically, so the web app does not set headers itself. Examples below use `-b`.

### 5.1 GET /api/me

**Sample request**

```bash
curl -sS https://unpack.example.com/api/me -b "unpack_session=<session>"
```

**Response `200`**

```json
{
  "login": "mara-dev",
  "avatar_url": "https://avatars.githubusercontent.com/u/1234567?v=4"
}
```

### 5.2 GET /api/analyses/{public_id}

The full analysis: summary, graph, impact, reasons, findings and diff hunks. The shape is `AnalysisResponse` in `server/app/schemas/api.py`.

**Path parameter:** `public_id`.

**Responses**

| Status | When | Body |
|---|---|---|
| 200 | Analysis done | Full model (below) |
| 200 | Queued or running | `{"analysis": {"public_id", "status"}}` with `Retry-After: 3` |
| 200 | Failed | `{"analysis": {"public_id", "status": "failed", "error_code", "error_message"}, "repo", "branch", "head_sha", "short_sha"}` |
| 403 | No access to the repository | `no_repo_access` |
| 404 | No such analysis | `not_found` |

**Full model (done)**

| Field | Type | Notes |
|---|---|---|
| `analysis` | object | `public_id`, `status`, `repo`, `branch`, `base_sha`, `head_sha`, `short_sha`, `created_at`, `finished_at`, `agent`, `llm_model`, `prompt_version`, `has_session` |
| `pull_request` | object or null | `{number, title, url, state}` |
| `banner` | object or null | `{kind, message}`. `kind` is `partial_coverage`, `out_of_date`, `reasons_unavailable` or `no_session` |
| `summary` | string | |
| `stats` | object | `functions_changed`, `by_source`, `by_change`, `not_reached_by_tests` |
| `facts` | object | `last_test_run`, `tested_after_final_edit` |
| `graph` | object | `nodes[]`, `edges[]`, `collapsed[]`, `truncated` |
| `reading_order` | array of string | Node IDs |
| `impact` | object | `summary`, `by_node` |
| `timeline` | array | Session turns with `kind`, `ts`, `label`, `nodes` |
| `reasons` | object | Node ID to `{reason, driver, history, confidence, source, evidence}` |
| `findings` | array | Review findings: `{id, kind, finding, functions, evidence}` |
| `diff_hunks` | object | File path to `[{start_line, end_line, patch}]` |

**Sample request**

```bash
curl -sS https://unpack.example.com/api/analyses/q7Lk2mT9xVbR4sYc8nHwFA -b "unpack_session=<session>"
```

**Sample response `200`** (trimmed)

```json
{
  "analysis": {
    "public_id": "q7Lk2mT9xVbR4sYc8nHwFA",
    "status": "done",
    "repo": {"owner": "acme", "name": "billing", "default_branch": "main"},
    "branch": "feat/invoice-rounding",
    "base_sha": "3f2a9c1d7e4b8a60c5d91f2e3a7b4c8d9e0f1a2b",
    "head_sha": "9b8e4d2a1c7f6e5d3b0a9c8f7e6d5c4b3a2f1e0d",
    "short_sha": "9b8e4d2",
    "created_at": "2026-11-20T09:15:10Z",
    "finished_at": "2026-11-20T09:16:02Z",
    "agent": "claude_code",
    "llm_model": null,
    "prompt_version": 1,
    "has_session": true
  },
  "pull_request": {
    "number": 42,
    "title": "Round invoice totals to cents",
    "url": "https://github.com/acme/billing/pull/42",
    "state": "open"
  },
  "banner": null,
  "summary": "Invoice totals are now rounded to cents before tax is applied.",
  "stats": {
    "functions_changed": 2,
    "by_source": {"session": 2},
    "by_change": {"added": 1, "functional": 1},
    "not_reached_by_tests": 1
  },
  "facts": {
    "last_test_run": {"turn": "t14", "command": "pytest billing", "exit_code": 0, "summary": "12 passed"},
    "tested_after_final_edit": true
  },
  "graph": {
    "nodes": [
      {
        "id": "billing/invoice.py::round_total",
        "label": "round_total",
        "kind": "function",
        "parent": "billing/invoice.py",
        "path": "billing/invoice.py",
        "layer": "changed",
        "start_line": 18,
        "end_line": 24,
        "signature": "def round_total(amount: Decimal) -> Decimal",
        "is_async": false,
        "is_public": true,
        "change": {"kind": "added", "source": "session"},
        "test": {"label": "direct", "count": 3, "shortest_path": [], "nearest_tested": null},
        "callers_count": 2,
        "callees_count": 1,
        "is_test": false,
        "has_reason": true,
        "finding_ids": []
      }
    ],
    "edges": [
      {
        "id": "e1",
        "source": "billing/invoice.py::total",
        "target": "billing/invoice.py::round_total",
        "kind": "CALLS",
        "tier": "EXTRACTED",
        "via": null
      }
    ],
    "collapsed": [],
    "truncated": {"nodes_omitted": 0, "edges_omitted": 0}
  },
  "reading_order": ["billing/invoice.py::round_total", "billing/invoice.py::total"],
  "impact": {
    "summary": {"functions": 3, "files": 2, "public_api": 1, "uncertain_paths": 0},
    "by_node": {}
  },
  "timeline": [
    {"turn": "t3", "kind": "user_request", "ts": "2026-11-20T09:02:11Z", "label": "Round totals to cents", "nodes": []},
    {"turn": "t9", "kind": "edit", "ts": "2026-11-20T09:07:45Z", "label": "Edit invoice.py", "nodes": ["billing/invoice.py::round_total"], "reverted": false}
  ],
  "reasons": {
    "billing/invoice.py::round_total": {
      "reason": "Rounds half-up to the cent so totals match the printed invoice.",
      "driver": "user_asked",
      "history": [{"turn": "t3", "text": "Round totals to cents"}],
      "confidence": "high",
      "source": "session",
      "evidence": [{"turn": "t3", "quote": "Round totals to cents"}]
    }
  },
  "findings": [],
  "diff_hunks": {
    "billing/invoice.py": [{"start_line": 18, "end_line": 24, "patch": "@@ -18,4 +18,7 @@\n..."}]
  }
}
```

### 5.3 GET /api/analyses/{public_id}/turns

Returns the session turns the analysis refers to, so the UI can show the transcript for selected timeline items.

**Query parameters**

| Name | Type | Required | Notes |
|---|---|---|---|
| `ids` | string | yes | Comma-separated turn IDs, 1 to 50 |

**Sample request**

```bash
curl -sS "https://unpack.example.com/api/analyses/q7Lk2mT9xVbR4sYc8nHwFA/turns?ids=t3,t9" -b "unpack_session=<session>"
```

**Sample response `200`**

```json
{
  "turns": [
    {
      "turn_id": "t3",
      "kind": "user",
      "ts": "2026-11-20T09:02:11Z",
      "text": "Round totals to cents"
    },
    {
      "turn_id": "t9",
      "kind": "edit",
      "ts": "2026-11-20T09:07:45Z",
      "path": "billing/invoice.py",
      "excerpt": "+def round_total(amount: Decimal) -> Decimal:"
    }
  ]
}
```

**Errors:** `400 invalid_ids`, `403 no_repo_access`, `404 not_found`.

### 5.4 GET /api/analyses/{public_id}/nodes/{node_id}

Detail for one function, method, or class: source location, signature, callers and callees, tests, and imports. `node_id` can contain `/` and `::`, so it is matched as a path segment.

**Path parameters:** `public_id`, `node_id`.

**Sample request**

```bash
curl -sS "https://unpack.example.com/api/analyses/q7Lk2mT9xVbR4sYc8nHwFA/nodes/billing/invoice.py::round_total" -b "unpack_session=<session>"
```

**Sample response `200`** (trimmed)

```json
{
  "node": {
    "id": "billing/invoice.py::round_total",
    "kind": "function",
    "path": "billing/invoice.py",
    "start_line": 18,
    "end_line": 24,
    "signature": "def round_total(amount: Decimal) -> Decimal",
    "decorators": [],
    "is_async": false,
    "is_public": true,
    "doc": "Round half-up to the cent.",
    "class": null
  },
  "change": {"kind": "added", "source": "session"},
  "source_head": "def round_total(amount: Decimal) -> Decimal:\n    ...",
  "diff": [{"start_line": 18, "end_line": 24, "patch": "@@ -0,0 +18,7 @@\n..."}],
  "callers": [{"id": "billing/invoice.py::total", "tier": "EXTRACTED", "via": null, "line": 31, "in_graph": true}],
  "callees": [],
  "callers_total": 1,
  "callees_total": 0,
  "unresolved_calls": [],
  "file_imports": [{"module": "decimal", "names": ["Decimal"], "context": "runtime"}],
  "file_imported_by": ["billing/report.py"],
  "tests": {
    "label": "direct",
    "count": 3,
    "paths": [["tests/test_invoice.py::test_round_half_up"]],
    "nearest_tested": null
  },
  "impact": []
}
```

`change` is `null` for nodes that did not change. `callers` and `callees` are capped in the response; `callers_total` and `callees_total` give the full counts.

**Errors:** `403 no_repo_access`, `404 not_found` (analysis not finished, or no such node), `404` if the graph is unavailable.

### 5.5 GET /api/prs/{owner}/{repo}/{number}/analyses

The analyses linked to a pull request, newest first (up to 50). The UI uses this for the commit picker.

**Path parameters:** `owner`, `repo`, `number` (integer).

**Sample request**

```bash
curl -sS https://unpack.example.com/api/prs/acme/billing/42/analyses -b "unpack_session=<session>"
```

**Sample response `200`**

```json
{
  "pull_request": {
    "number": 42,
    "title": "Round invoice totals to cents",
    "url": "https://github.com/acme/billing/pull/42",
    "state": "open"
  },
  "analyses": [
    {
      "public_id": "q7Lk2mT9xVbR4sYc8nHwFA",
      "head_sha": "9b8e4d2a1c7f6e5d3b0a9c8f7e6d5c4b3a2f1e0d",
      "short_sha": "9b8e4d2",
      "commit_message": "Round invoice totals to cents",
      "created_at": "2026-11-20T09:15:10Z",
      "status": "done",
      "is_published": true
    }
  ]
}
```

**Errors:** `403 no_repo_access`, `404 not_found` (no such repository or pull request).

### 5.6 GET /api/repos/{owner}/{repo}/map

The codebase map at a commit: one row per folder, file, class, or function. Used for the map view.

**Query parameters:** `sha` (required, 40 hex characters).

**Headers:** `If-None-Match` (optional). The response ETag is `"<sha>"`. A matching value returns `304` with no body. The response is cached privately for one day.

**Sample request**

```bash
curl -sS "https://unpack.example.com/api/repos/acme/billing/map?sha=9b8e4d2a1c7f6e5d3b0a9c8f7e6d5c4b3a2f1e0d" -b "unpack_session=<session>"
```

**Sample response `200`** (trimmed)

```json
{
  "repo": {"owner": "acme", "name": "billing", "default_branch": "main"},
  "map_sha": "9b8e4d2a1c7f6e5d3b0a9c8f7e6d5c4b3a2f1e0d",
  "columns": ["id", "kind", "parent", "loc", "fan_in", "is_test"],
  "nodes": [
    ["billing", "folder", null, 412, 0, false],
    ["billing/invoice.py", "file", "billing", 188, 4, false],
    ["billing/invoice.py::round_total", "function", "billing/invoice.py", 7, 2, false]
  ],
  "counts": {"folders": 1, "files": 1, "classes": 0, "functions": 1, "tests": 0}
}
```

Each row in `nodes` follows `columns`.

**Errors:** `400 invalid_payload` (bad `sha`), `403 no_repo_access`, `404 not_found`.

### 5.7 GET /api/repos/{owner}/{repo}/nodes/{node_id}/edges

Callers and callees of one node at a commit. Used to expand the graph in the UI.

**Query parameters:** `sha` (required, 40 hex characters).

**Sample request**

```bash
curl -sS "https://unpack.example.com/api/repos/acme/billing/nodes/billing/invoice.py::round_total/edges?sha=9b8e4d2a1c7f6e5d3b0a9c8f7e6d5c4b3a2f1e0d" -b "unpack_session=<session>"
```

**Sample response `200`**

```json
{
  "id": "billing/invoice.py::round_total",
  "callers": [{"id": "billing/invoice.py::total", "tier": "EXTRACTED"}],
  "callees": [],
  "callers_total": 1,
  "callees_total": 0
}
```

The lists are capped at 200 entries each. The `*_total` fields give the full counts.

**Errors:** `400 invalid_payload` (bad `sha`), `403 no_repo_access`, `404 not_found` (no such node), `404` if the graph is unavailable.

## 6. Pages and images

### 6.1 GET /a/{public_id}

The web app page for an analysis. It returns the built `index.html`. The page then calls the `/api/*` endpoints with the viewer's cookie.

**Response `200`** (`text/html`). The response carries the Content-Security-Policy header: `default-src 'self'; img-src 'self' https://avatars.githubusercontent.com data:; style-src 'self' 'unsafe-inline'; …`. Inline scripts are blocked, so the page loads `/assets/*.js` instead.

**Response `503`** if the web app is not built.

### 6.2 GET /img/{file_name}

Serves a rendered analysis image. `file_name` is 32 hex characters. GitHub's image proxy caches by URL, so the name is random and never reused.

**Sample request**

```bash
curl -sS -o analysis.png https://unpack.example.com/img/3c9e1f0a7b2d4e6f8a1c3b5d7e9f0a2b
```

**Response `200`:** `Content-Type: image/png`, 1200 × 700 CSS pixels at 2× (2400 × 1400 pixels). **Errors:** `404 not_found`.

### 6.3 GET /render/{public_id}

Internal. The renderer loads this page in Chromium to make the image. It is refused unless the caller is on loopback or a private network, and the `render_token` is valid.

**Query parameters:** `render_token`. Created by the server with HMAC-SHA256 over `public_id` and an expiry time. The token is valid for 60 seconds.

**Responses:** `200` (`text/html`) when valid. `403 forbidden` when the caller is external or the token is missing, invalid, or expired. `503` if the web app is not built.

The rendered page sets `data-ready` when it has drawn, or `data-error` if it failed. The renderer waits for one of these.

### 6.4 GET /favicon.ico

Returns `204 No Content`, with no body. Browsers use it to avoid a 404 for the icon.

## 7. Health

### 7.1 GET /healthz

The process is up. Does not check dependencies.

**Response `200`**

```json
{"ok": true}
```

### 7.2 GET /readyz

Checks Postgres and the worker's heartbeat (the worker writes one every 10 seconds).

**Response `200`** when healthy:

```json
{
  "postgres": "ok",
  "worker_heartbeat_age_s": 4,
  "worker": "ok"
}
```

**Response `503`** when any dependency fails (the body is the same, with `"failing"` in the failing field). `postgres` or `worker` is `"failing"`. A worker is failing if its heartbeat is older than 60 seconds, or missing.

## 8. Admin endpoints

All `/admin/*` endpoints need `Authorization: Bearer <ADMIN_TOKEN>`. A missing or wrong token returns `401 unauthorized`. The admin token is never stored in the database.

### 8.1 POST /admin/repos

Registers a repository and issues its ingest token. The token is shown once. Only its hash is stored.

The repository must have the GitHub App installed. The server asks GitHub which installation covers it.

**Request body** (`application/json`)

| Field | Type | Required | Default |
|---|---|---|---|
| `owner` | string | yes | |
| `name` | string | yes | |
| `default_branch` | string | no | `main` |

**Sample request**

```bash
curl -sS -X POST https://unpack.example.com/admin/repos \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"owner": "acme", "name": "billing", "default_branch": "main"}'
```

**Response `201`**

```json
{
  "repo_id": 7,
  "ingest_token": "unp_<ingest-token>",
  "installation_id": 53917204
}
```

**Errors:** `409 repo_exists`, `409 app_not_installed` (includes `details.install_url`), `503 app_not_configured`, `503 unavailable`.

### 8.2 POST /admin/repos/{repo_id}/rotate-token

Replaces the ingest token. The old token stops working at once.

**Sample request**

```bash
curl -sS -X POST https://unpack.example.com/admin/repos/7/rotate-token \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Response `200`**

```json
{"ingest_token": "unp_<ingest-token>"}
```

**Errors:** `404 not_found`.

### 8.3 POST /admin/repos/{repo_id}/graph/rebuild

Queues a graph build for a commit. Used after a change to the graph code, or to rebuild a broken graph.

**Request body** (optional)

| Field | Type | Notes |
|---|---|---|
| `sha` | string or null | 40 hex characters. Default: the head SHA of the repository's latest push |

**Sample request**

```bash
curl -sS -X POST https://unpack.example.com/admin/repos/7/graph/rebuild \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sha": "9b8e4d2a1c7f6e5d3b0a9c8f7e6d5c4b3a2f1e0d"}'
```

**Response `202`**

```json
{"job_id": 1184}
```

If an identical build is already queued or running, the new request is absorbed and `job_id` is `null`. **Errors:** `400 invalid_payload` (no push yet, and no `sha` given), `404 not_found`.

### 8.4 GET /admin/jobs

Lists the most recent queue jobs.

**Query parameters**

| Name | Type | Default | Notes |
|---|---|---|---|
| `status` | string | none | `queued`, `running`, `done` or `failed` |
| `type` | string | none | `analyze_push`, `render_image`, `publish_comment` or `build_graph` |
| `limit` | integer | 50 | 1 to 500 |

**Sample request**

```bash
curl -sS "https://unpack.example.com/admin/jobs?status=failed&limit=10" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Sample response `200`**

```json
{
  "jobs": [
    {
      "id": 1179,
      "type": "analyze_push",
      "status": "failed",
      "attempts": 4,
      "last_error": "gemini: timeout after 120s",
      "created_at": "2026-11-20T09:15:10+00:00"
    }
  ]
}
```

### 8.5 POST /admin/analyses/{public_id}/retry

Requeues a failed analysis. It clears the error and starts the analysis again.

**Sample request**

```bash
curl -sS -X POST https://unpack.example.com/admin/analyses/q7Lk2mT9xVbR4sYc8nHwFA/retry \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Response `202`**

```json
{"public_id": "q7Lk2mT9xVbR4sYc8nHwFA", "status": "queued"}
```

**Errors:** `404 not_found`, `409 not_failed`.

### 8.6 GET /admin/tracked-branches

Lists tracked branches (up to 200). The poller works through these.

**Query parameters:** `status` (optional): `waiting_for_pr`, `linked`, `closed_recently` or `abandoned`.

**Sample request**

```bash
curl -sS "https://unpack.example.com/admin/tracked-branches?status=waiting_for_pr" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Sample response `200`**

```json
{
  "branches": [
    {
      "id": 31,
      "repo": "acme/billing",
      "branch": "feat/invoice-rounding",
      "status": "waiting_for_pr",
      "latest_head_sha": "9b8e4d2a1c7f6e5d3b0a9c8f7e6d5c4b3a2f1e0d",
      "needs_publish": true
    }
  ]
}
```

A branch is tracked when it is pushed and is not the default branch. It moves to `abandoned` if no pull request appears within `PR_WAIT_DAYS` (default 3).

## 9. Behaviour that is not an endpoint

These are not HTTP endpoints, but a client depends on them.

- **Pull request comment and description.** The poller finds open pull requests for each tracked branch. It posts one comment per pull request, and updates that comment in place. It also writes an Unpack section at the top of the pull request description, between `<!-- unpack:begin -->` and `<!-- unpack:end -->`. Set `PR_DESCRIPTION_SECTION=false` to turn off the description section.
- **Installation sync.** The poller refreshes installations from GitHub every `INSTALLATION_SYNC_SECONDS` (default 900). It replaces the webhook.
- **Analysis link.** The comment links to `/a/{public_id}`. An on-demand "run analysis" link is not part of this build.

## 10. Changes from the earlier design

| Earlier | Now |
|---|---|
| `POST /github/webhook` (HMAC-signed) | Removed. The poller finds changes |
| `POST /admin/tracked-branches/{id}/check-now` | Removed |
| `tracking.next_check_at` in the ingest response | Removed. Response has `tracking.status` only |
| `GITHUB_WEBHOOK_SECRET`, `TRACK_MAX_DAYS` | Removed |
| Branch hold of 7 days | `PR_WAIT_DAYS` (default 3) |
| Reconcile every 2 minutes | `RECONCILE_INTERVAL_SECONDS` (default 10) |

See `docs/server-design.md` (its "Revised decisions" note) for the reasons.
