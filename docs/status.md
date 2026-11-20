# Status: what is built, verified and open

Verified against `main` at `7ad132c` (merge of PR #12, `integrate/graph-stack`), on 2026-11-20. This replaces the earlier gap analysis (`server-changes.md`), which described the repository at `fef368c`.

Each design document says what should exist. This document says what does exist, what was checked, and what is still open.

## 1. How this was verified

| Check | Result |
|---|---|
| `main` fetched from `origin`; local `main` fast-forwarded from `fef368c` to `7ad132c` | Done. The working branch `claude/optimistic-bell-k7d1gf` is at the same commit |
| `pip install -e ".[dev]"` | Installed |
| `pytest tests/` with no Postgres | 72 passed, 3 skipped, **33 errors**: every server test needs Postgres on `localhost:5432` |
| Local Postgres 16, database `unpack_test`, user `unpack` | Started in the sandbox |
| `pytest tests/` with Postgres | **105 passed, 3 skipped.** The 3 skipped are the Neo4j tests (no Neo4j running) |
| `pytest tests/ -n auto` on the server branch, after the poller work and the boot-time sync fix (§9) | **147 passed, 4 skipped.** The 4 skips need a launchable Chromium |
| `alembic upgrade head` on a fresh database, then `alembic check` | Passes. `downgrade base` also exits 0 |
| Neo4j tests | Not run. Neo4j is not running in this environment |
| Web build (`npm ci`, `npm run build`) | **Not verified.** The install step was blocked by the session's permission policy. The earlier claim that `App.tsx` fails `tsc` on an unused `React` import is unchecked |
| Docker build (`server/Dockerfile`) | **Not verified.** Docker is present but no build was run |
| Real GitHub App, OAuth app and webhook delivery | **Not verified.** All GitHub calls are mocked in tests |
| Gemini API calls | **Not verified.** The reasoning step is a placeholder |
| Chromium render | Carried over from the earlier draft: a 2400 × 1400 PNG (1200 × 700 at 2×), 56 KB, passed the blank check. Not re-run in this check |
| Design documents against code | Read and compared in this check; see §3 |

## 2. What is built, placeholder and missing

| Area | Design | On main | State |
|---|---|---|---|
| CLI: install, uninstall, status | [cli-hook.md §2](cli-hook.md#2-commands) | `cli/main.py`, `cli/hook.py`, `cli/config.py` | **Built** |
| CLI: push and dry run | [cli-hook.md §2](cli-hook.md#2-commands) | `unpack push` with `--dry-run` | **Built** |
| CLI: commits, diff, changed files | [cli-hook.md §4, §7](cli-hook.md#4-choosing-the-commits) | `cli/git_info.py` | **Built** |
| CLI: session finding and trimming | [cli-hook.md §5](cli-hook.md#5-finding-and-trimming-the-session) | `cli/session_finder.py` | **Built** (Gemini CLI only) |
| CLI: secret scanning | [cli-hook.md §6](cli-hook.md#6-removing-secrets) | `cli/secrets.py` (exact values, patterns, entropy) | **Built** |
| CLI: ingest transport | [cli-hook.md §7](cli-hook.md#7-the-payload) | `cli/transport.py`, gzip, bearer token | **Built** |
| CLI: mock server | [cli-hook.md §2](cli-hook.md#2-commands) | `cli/mock_server.py` (`unpack mock-server`) | **Built** |
| Ingest and push status | [server §5.1, §5.2](server-design.md#51-post-v1ingest-cli-hook) | `routers/ingest.py` | **Built** |
| Config, fail-fast secrets | [server §12](server-design.md#12-configuration-env) | `config.py`: required values, minimum lengths, Fernet check | **Built** |
| Data model and migrations | [server §4](server-design.md#4-data-model-postgres) | `models.py`, `server/migrations/versions/19c3f5677b8a_baseline_schema.py` | **Built** (Alembic baseline) |
| Queue, worker, heartbeat | [server §6](server-design.md#6-jobs-and-the-worker) | `jobs/queue.py` (`SKIP LOCKED`), `jobs/worker.py`, `jobs/handlers.py` | **Built** |
| Reconciler | [server §3](server-design.md#3-linking-pushes-to-prs-track-the-branch-reconcile-on-a-timer) | `jobs/reconciler.py` | **Built** |
| Publishing the comment | [server §3.5, §8.3](server-design.md#8-github-app-and-the-pr-comment) | `jobs/publish.py`, `github/comments.py` | **Built** |
| GitHub App auth and PR calls | [server §8.2](server-design.md#82-authentication) | `github/service.py`, `github/prs.py` | **Built** (mocked tests) |
| Change classification | [session §4.3](session-pipeline.md#43-find-the-changed-functions-facts) | `pipeline/changes.py` (reuses `unpack_graph.diff._flags`) | **Built** |
| Analysis facts: graph, impact, reading order, timeline | [server §6](server-design.md#6-jobs-and-the-worker) | `pipeline/analysis.py`, `pipeline/graph_view.py` | **Built.** The timeline comes from the reasoning step, so it is empty until that step exists |
| §5.5 validation before storing | [server §5.5](server-design.md#55-live-graph) | `graph_view.validate_graph_view` | **Built** |
| Session parsing into turns | [session §4.2](session-pipeline.md#42-parse-the-session-into-turns) | none. The session row is stored with `turns = []` | **Missing** |
| Edit-to-function mapping and linking | [session §4.4, §4.5](session-pipeline.md#44-map-each-session-edit-to-functions-facts) | none | **Missing** |
| LLM input building and trimming | [session §4.6](session-pipeline.md#46-build-the-llm-input) | none | **Missing** |
| Gemini client, retries, fallback, repair | [server §7](server-design.md#7-gemini-api-llm-calls) | none (`llm/placeholder.py` only) | **Missing** |
| Prompt files | [server §7.8](server-design.md#78-prompts-and-versions) | `llm/prompts/reasons_v1.md`, `json_repair_v1.md` present; content not reviewed in this check | **Present, unreviewed** |
| Verification of quotes and facts | [session §4.8](session-pipeline.md#48-verify-code) | none | **Missing** |
| Reasons and findings in the API | [server §5.5](server-design.md#55-live-graph) | empty `reasons` and `findings`; banner `reasons_unavailable` (or `no_session`) | **Placeholder** |
| Render and image | [server §9](server-design.md#9-rendering-the-image-must-never-be-wrong) | `jobs/render.py`, `routers/images.py` (1200 × 700, 2× scale, 2 MB limit, blank check, `/render` token) | **Built** (see §1) |
| Live API | [server §5.5](server-design.md#55-live-graph), [§5.6](server-design.md#56-images-and-rendering) | `routers/live.py`: analysis, turns, node detail, commit picker, map with ETag, node edges | **Built** |
| Viewer login and access check | [server §5.4](server-design.md#54-viewer-login) | `routers/auth.py`, `deps.py`: OAuth, Fernet-encrypted tokens, 10-minute access cache | **Built** (not tested against GitHub) |
| GitHub setup and poller | [server §5.3](server-design.md#53-github) | `routers/github_setup.py`, `jobs/reconciler.py`: no webhook; the poller and installation sync replace it (§9) | **Built** (mocked tests; not tested against GitHub) |
| Admin | [server §5.7](server-design.md#57-operations-and-admin) | `routers/admin.py` | **Built** |
| Health | [server §5.7](server-design.md#57-operations-and-admin) | `/healthz`, `/readyz` (Postgres and worker heartbeat); no CORS middleware | **Built** |
| Code graph library | [graph-design.md](graph-design.md) | `unpack_graph/`: pass 1, pass 2, reachability, change detection, region, incremental, Neo4j loader | **Built** (Python only) |
| Neo4j in production | [server §1](server-design.md#1-architecture) | Removed from `docker-compose.yml`; not used by the server | **Deviation** (D1) |
| Contract schemas | [server §2.1](server-design.md#21-building-the-ui-in-parallel-the-contract) | 7 JSON schemas in `contract/schema/` | **Built** |
| Contract fixtures | [ui-design §8.1](ui-design.md#81-hour-1-contract-shared-with-the-server) | `contract/fixtures/analysis_done.json` only | **Partial** (running, failed, no-session, nodes, turns, PR analyses and map are missing) |
| Web UI | [ui-design.md](ui-design.md) | `web/src/App.tsx`, `main.tsx`: one placeholder page. UI packages declared in `package.json` | **Stub** |
| Dockerfile | [server §14](server-design.md#14-running-it) | Multi-stage. Sources are copied before the editable install | **Not verified.** Note: the UI build step uses `npm run build \|\| mkdir -p dist && touch dist/index.html`, so a failed UI build still produces an image with an empty page |
| `docker-compose.yml` | [server §14](server-design.md#14-running-it) | `postgres`, `api`, `worker`, `cloudflared` (profile `tunnel`) | **Built** (no Neo4j) |

## 3. Design documents against code

Each design document was read against `main`. Differences that matter:

| Document | Says | Main | Where it is recorded |
|---|---|---|---|
| Server design §1, §4, §13 | Neo4j stores the code graph | Not used. Pickled graphs under `DATA_DIR/graphs` | [server §17 D1](server-design.md#17-decisions-and-deviations) |
| Server design §5.5 | Graph view from `region` | Server builds its own API graph from `build_graph`. `region.py` is for the CLI | [server §17 D5](server-design.md#17-decisions-and-deviations) |
| Server design §13 | `llm/client.py`, `llm/schemas.py`, `pipeline/session_gemini.py`, `pipeline/llm_input.py`, `pipeline/verify.py` | Not present | §2 above |
| Server design §5.7 | `/readyz` checks Neo4j | Checks Postgres and the worker only | [server §5.7](server-design.md#57-operations-and-admin) |
| Session pipeline §3.5 | Posts to `{server}/ingest` | `POST /v1/ingest` | [session §8](session-pipeline.md#8-conflicts-resolved-against-the-server-design) |
| Session pipeline §4.7 | `temperature 0`; `history` as a string | Not implemented yet. Model default; `history` is a string in the API | [session §8](session-pipeline.md#8-conflicts-resolved-against-the-server-design), §4 below |
| UI §3.2 | Node kind `module` | Server uses `file`, `class`, `function`, `method`, `test` | [ui-design §3.2](ui-design.md#32-node-types-and-shapes) |
| UI §3.4 | `history` as a vertical timeline | `FunctionReason.history: str \| None` | §4 below |
| Buildathon plan | Gemini on AI Studio; Neo4j; Sigma for everything | As in [product-plan §7](product-plan.md#7-changes-since-the-first-plan) | product-plan §7 |

## 4. Open decisions

These need a decision before the reasoning step or the UI is built. None blocks the server's current behaviour.

| # | Question | Options | Recommendation |
|---|---|---|---|
| O1 | Shape of `history` (per function) | (a) keep one string; (b) a list of `{turn, text}` steps, which the UI timeline needs | (b). It is a contract change: edit `api.py` first, then `make contract`, then the fixtures and the UI types |
| O2 | Where rejected quotes go | (a) `analyses.llm_raw`; (b) a new column | (a) for the demo. Add a column later if the debugging need grows |
| O3 | Content-Security-Policy for React Flow and ELK | (a) keep `default-src 'self'` and add `style-src 'self' 'unsafe-inline'`, `worker-src 'self' blob:` as needed; (b) relax further | (a), confirmed in a browser before the demo |
| O4 | Gemini model names | Check each name with a real call the day before the demo. Keep the stored analysis as the fallback | Do this before any recording or demo |
| O5 | Viewer login for the demo | (a) keep GitHub OAuth (built); (b) one allowed account | (a) is already built; keep it unless it blocks the demo |
| O6 | Whether `reasons_part` splitting is built | (a) build it; (b) skip it for the demo, since the demo session is small | (b) for the demo; keep the design |
| O7 | Whether the commit trailer is built | Deferred in the plan | Deferred |

## 5. Gaps against the demo path

In the order they block the demo (push to PR comment to live graph):

1. **Session parser** (`session §4.2`). Without it there are no turns, no edit links, and no timeline. Test it on three real Gemini CLI sessions first.
2. **Edit mapping and linking** (`session §4.4`, `§4.5`). These give each function its source label.
3. **Gemini client and reasons step** (`server §7`), with the verification in `session §4.8`. This is where the reasons and evidence come from. Use the fake-client fixtures for tests.
4. **Fixtures** for the UI: running, failed, no-session, node detail, turns, PR analyses and a real map (`ui-design §8.1`).
5. **The UI** (`ui-design.md`): PR view, detail panel, change list, static mode. The core tier is about 5 hours of work in the estimate.
6. **A real end-to-end run.** Build the Docker image, run it, push the demo session, and check the comment and the live page. None of this has been run in this check.
7. **Real GitHub App and OAuth.** Not tested against GitHub.

## 6. Smaller items to fix

- **Root `README.md` is out of date.** It shows Neo4j in `docker-compose.yml` and `docker compose up -d neo4j`, lists the reasoning engine and PR view as built, and says the project includes `docs/graph-design.md` only. Update it to match this status (outside `docs/`; not changed in this pass).
- **`server/Dockerfile`** hides a failed UI build with `|| mkdir -p dist && touch dist/index.html`. Remove the fallback once the UI builds.
- **`unpack_graph/neo4j_io.py`** and its tests stay, but nothing in the server uses them. Keep them as an optional loader, or remove them later.
- **`pyproject.toml`** still lists `neo4j`, which the server does not need. It is needed by the library's optional loader.
- **Contract fixtures** are one file short of what the UI needs (§2).
- **Session format** has not been checked against real Gemini CLI sessions in this check. The source commit `808199f` could not be read from here.

## 7. Documentation changes in this pass

| Document | Change |
|---|---|
| `docs/README.md` | New: index and reading order |
| `docs/product-plan.md` | New: the buildathon plan, updated with current status and decisions (§7 lists the changes) |
| `docs/cli-hook.md` | New: CLI and hook, built |
| `docs/session-pipeline.md` | New: from the session pipeline design, with conflicts resolved |
| `docs/server-design.md` | New: from the latest server design, with the code layout and decisions (§17) |
| `docs/ui-design.md` | New: from the UI design, with status and open items |
| `docs/graph-design.md` | Updated: Neo4j references corrected, validation counts clarified, and new sections on build history, server use and glossary |
| `docs/status.md` | New: replaces `docs/server-changes.md` |
| `docs/server-changes.md` | Removed. Its gap table and build order are now in this document and the server design |

## 8. Changes on the server branch after `7ad132c`

This section records what changed on `claude/gifted-heisenberg-j9b1dk` (PR #14) after the check above. It also settles some rows of §1: the Docker build and a container run are now verified, and the UI build failure is confirmed.

**Audit against the design.** Every endpoint in design §5 is served (27 routes; see `/openapi.json`). Fixed in this pass:

- `needs_publish` now clears once every open PR shows the latest analysis. The publish step recalculates it.
- A PR behind an older analysis gets the newest ancestor analysis after 10 minutes (design §3.3). Before, nothing was published.
- Node detail returns `callers_total`, `callees_total` and `unresolved_calls`. The contract schema is regenerated.
- Map folder rows carry line totals.
- The map and node endpoints return 404 for a commit the server cannot reach, instead of 500.
- OAuth login states are single use (`oauth_states` table).
- Graph output no longer depends on set iteration order across processes.
- Compose has a `migrate` service; the API and worker wait for it.

**Performance** (SQLAlchemy, 258 files, about 11,700 functions, one changed function):

| Case | Before | After |
|---|---|---|
| Analysis, cold base | 20.1 s (full base and full head) | 14.3 s (base built and cached; head incremental) |
| Analysis, warm base | 20.1 s | 8.1 s |
| Four analyses | 32.8 s, sequential | 14.3 s with `ANALYSIS_PROCESSES=2` |

- The base graph is cached per base commit. The head is built with the library's `update_graph` on top of it. A test checks that the result equals a full rebuild.
- Analyses run in `ANALYSIS_PROCESSES` worker processes.
- One Chromium per process, reused across renders.
- Reconciler branch checks run concurrently.
- Node detail reads one blob instead of listing the repository tree.
- Indexes for the job claim, the due-branch scan, the push rate limit and PR lookups.
- Graph cache files use unique temp names, are pruned per repository, and a small in-memory LRU serves the read endpoints.

**Tests.** 131 passed, 4 skipped, with `pytest tests/ -n auto` (about 26 s; about 62 s serially). Each xdist worker has its own database, and each test has its own data directory and graph cache. The four skips need a launchable Chromium.

**Container verification** (this supersedes the "not verified" rows for Docker above):

- The image builds from `server/Dockerfile`, including the pip install, the Playwright browser install and the web stage. The sandbox's proxy CA was passed as a named build context, not committed.
- Chromium launches inside the container. Migrations are present.
- The compose stack comes up healthy: Postgres, then `migrate` (exit 0), then the API and worker. `/healthz` and `/readyz` pass, and the worker heartbeat is fresh.
- End to end: a repository is registered, a push goes through `POST /v1/ingest` (202), the worker clones from a git origin inside its container, and the analysis finishes with the expected facts (two functions changed: one added, one functional; one not reached by tests).
- Rendering: the worker renders through the API's internal `/render` route and produces a 2400 × 1400 PNG. The public `/img` route serves it.
- Migrations are idempotent.

**Found and fixed in the container run:** the worker rendered against `127.0.0.1:8000`, which is the worker's own loopback. Every render failed with connection refused. The compose worker now sets `INTERNAL_API_URL=http://api:8000`.

**Confirmed, UI side:** the web bundle does not build. `web/src/App.tsx` fails `tsc` on an unused `React` import (`TS6133`). The Dockerfile's fallback (`npm run build || … touch dist/index.html`) then ships an empty `index.html`, which hides the failure. The live page and the comment image cannot render until the UI builds.

**Still open:**
- `web/` has no lockfile, so `npm ci` falls back to `npm install` and the install is not reproducible.
- The Dockerfile's fallback should fail the build once the UI is ready.
- Real GitHub App, OAuth and webhook delivery: still mocked in tests.
- The CLI hook against a real push.
- The webhook replacement is built: see §9.


## 9. Poller replaces webhooks

The decisions below were made after the container checks in §8. They are built and tested on this branch.

| Decision | Built as |
|---|---|
| No webhooks | `/github/webhook`, `GITHUB_WEBHOOK_SECRET` and the `webhook_deliveries` table are removed (migration `412bc53b2425`). `/github/setup` stays, because the install flow needs a page. |
| Poller every 10 s | `RECONCILE_INTERVAL_SECONDS=10`. One sweep covers every active branch. |
| One conditional call per repository | `GET /repos/{o}/{r}/pulls` with `If-None-Match`. A 304 costs no rate-limit budget and reuses the stored list. |
| Compare cache | `pull_requests.compare_cache` keyed by `(PR head, latest head)`. An unchanged pair is never compared twice. |
| Installation sync | Every `INSTALLATION_SYNC_SECONDS` (900) from `GET /app/installations`, replacing the installation webhooks. |
| Hold for a PR | `PR_WAIT_DAYS=3` (configurable). After that the branch is `abandoned`. |
| One comment per PR | Unchanged: updated in place, as before. |
| Section at the top of the PR description | `PR_DESCRIPTION_SECTION=true`. Written between `<!-- unpack:begin -->` and `<!-- unpack:end -->`; the author's text is never changed. |
| Trigger to post after the hold | **Not built.** Deferred, as agreed. |

**Schema:** `tracked_branches.next_check_at` and its index are removed, and `needs_publish` now means "a post is outstanding". New columns: `repos.pulls_etag`, `pull_requests.compare_cache`, `pull_requests.description_hash`. New index: `ix_tracked_sweep`.

**Tests:** 147 passed, 4 skipped, with `pytest tests/ -n auto`. New module `test_poller.py` covers the defaults, the webhook route being gone, the 3-day hold and its setting, the 304 path, the compare cache, and the description section (placed at the top, author text kept, unchanged content not rewritten). The webhook and per-branch timing tests were replaced.

**Found and fixed while checking the poller in the container:**
- The first installation sync after boot was skipped on a host that had been up for less than the sync interval. The sentinel was `0.0`, but `time.monotonic()` counts from boot, so the check looked like "synced recently". The sentinel is now `None` (never synced), with a test for a young host.
- The merge migration `b398e9b017ae` had unused imports (ruff F401). They are removed; the migration logic is unchanged.
- The installation sync retried on every 10-second sweep after a failure. It now retries after about a minute, and the test for that is in place.
- The setup page returned 500 when GitHub could not be reached. It now returns 503 with a clear message.
- The first sweep marks a repository `app_missing` when the App does not list it. That matches GitHub and is correct; the test fake now lists the test repository as installed.

**Container check of this change:** the stack ran with the repository's current `server/` mounted over the image's copy, because a fresh image build could not finish in this sandbox (BuildKit's session dropped during the export step). The image's dependencies are unchanged by this work, so the mount exercises the new code on the same environment. A proper rebuild is still to do. What was checked: the migration applied to the new head (`412bc53b2425`), `/github/webhook` returns 404, `/readyz` passes, a push is analysed and held as `waiting_for_pr`, and the worker's sweeps run without errors.

**Known limits:**
- A PR that is closed or merged is noticed while its branch is active. After the branch is `closed_recently`, a reopened PR is not noticed until a new push.
- The description section makes the PR body edit (`PATCH /pulls/{n}`), which needs the App's pull-requests write permission (already required by the comment).
- Polling uses the installation token for each repository with active branches. Abandoned branches are not polled.
