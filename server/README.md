# Unpack server

A FastAPI application plus a background worker. The API takes uploads from the CLI and serves the web UI; the worker turns each push into an analysis.

```bash
docker compose up -d postgres          # from the repository root
alembic -c server/alembic.ini upgrade head
make dev-server                        # API on :8000
make dev-worker                        # worker and branch reconciler
```

## What runs

- **API** (`app/main.py`, `app/routers/`): ingest, the live analysis API, dashboards, governance, GitHub setup, auth, admin and rendered images. It also serves the built web UI, so one process answers everything at `/`.
- **Worker** (`app/jobs/`): takes jobs from a Postgres queue (`SELECT ... FOR UPDATE SKIP LOCKED`), runs analyses, publishes PR comments and renders images.
- **Reconciler** (`app/jobs/reconciler.py`): tracks pushed branches, finds their pull requests and keeps one comment per PR up to date. It only re-publishes a PR whose comment does not already show the latest analysis.

## The analysis pipeline

`app/pipeline/analysis.py` runs these steps for each push:

| Step | Module | Uses an LLM |
|---|---|---|
| Build the code graph at the pushed commit | `build.py`, `unpack_graph/` | No |
| Find changed functions and classify the change | `changes.py`, `diff_files.py` | No |
| Parse the session into turns | `session.py`, `agy_session.py` | No |
| Map each session edit to functions | `edit_linker.py` | No |
| Reason about each change, with evidence | `llm/`, `prompts/reasons_*.md` | Yes |
| Verify quotes and claims | `verify.py` | No |
| Reading flow of the change | `flow.py` | Yes |
| Decisions, human overrides and steering rules | `decisions.py`, `steering.py` | Yes |
| Roll decisions up into dashboard rows | `rollup.py`, `metrics.py` | No |

The governance step never fails an analysis: if it breaks, the graph and reasons are still stored. See [docs/session-pipeline.md](../docs/session-pipeline.md) and [docs/governance-pipeline.md](../docs/governance-pipeline.md).

## API

| Area | Endpoints |
|---|---|
| CLI | `POST /v1/ingest` (gzip, bearer token) |
| Analysis | `GET /api/analyses`, `GET /api/analyses/{id}`, `.../turns`, node and edge details |
| Dashboards | `GET /api/dashboard/exec`, `/repos`, `/repo`, `/teams` |
| Governance | `GET /api/governance`, approve, reject, watch, retire, renew, revise, relax |
| Ops | `/healthz`, `/readyz`, `/admin/*` |

Full request and response shapes: [docs/api-contract.md](../docs/api-contract.md). JSON Schemas are exported with `make contract`.

## Configuration

Settings live in `app/config.py` and are read from the environment (see [`.env.example`](../.env.example)). Required secrets must be set and long enough or the server will not start.

Database changes go through Alembic migrations in `migrations/`. Create one with `alembic -c server/alembic.ini revision --autogenerate -m "..."`.

## Tests

```bash
pytest tests/server -n auto            # needs Postgres on localhost:5432
```

The LLM is replaced by a mock in the tests (`app/llm/mock.py`), so they need no API key.

Design: [docs/server-design.md](../docs/server-design.md).
