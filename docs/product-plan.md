# Unpack: product plan and buildathon scope

Status of this document: updated 2026-11-20 against `main` at `7ad132c`. It started as the buildathon plan (19 Nov 2026). Where the designs were later refined, the detailed design documents win; [section 7](#7-changes-since-the-first-plan) records each change.

Related documents: [server design](server-design.md), [CLI and hook](cli-hook.md), [session pipeline](session-pipeline.md), [UI design](ui-design.md), [code graph](graph-design.md), [current status](status.md).

## 1. What Unpack is

**Unpack helps teams understand code they did not write themselves.** For every pull request an AI agent produces, it shows what changed in the codebase, why each decision was made and which parts are untested, as a graph you can explore instead of a diff you read line by line.

**Code comprehension is the new bottleneck.** Agents write code far faster than people can understand it. Unpack keeps human understanding in step with AI output, so the people who own the code can still explain it, review it and fix it.

When agents write, review and merge more code, the people who come back to it later (a reviewer, an on-call engineer, an incident commander) have no quick way to see what changed or why. Unpack closes that gap.

**Where Unpack stands apart.** Tools such as Entire and Git AI *record* agent sessions next to commits, and review bots such as CodeRabbit *summarise* diffs. Unpack extracts the reasoning for each function from the session, backs every reason with evidence, and shows it on an explorable graph of the codebase.

## 2. Goal for the buildathon

Show one complete path: a developer pushes AI-written code, and the pull request gets an explained, explorable graph of the change.

1. **The developer works with an agent**, writes code, pushes and opens a pull request. For now, assume one agent session per push.
2. **The CLI hook fetches that session** and sends it to the Unpack server with the push: the code change and the actions taken.
3. **The server processes it.** It works out what changed and why, and produces a short summary plus a graph of the changed part of the codebase, with the changes highlighted.
4. **Unpack posts a comment on the pull request** with the summary, a static image of the graph and a link to the live graph.
5. **Clicking the link opens the interactive graph**, where the viewer explores the change and reads the reasoning behind each part.

The demo is a Gemini CLI session on an httpx fork: a feature added to both `Client` and `AsyncClient`, tests only on the sync path, a failed test run and a fix, one formatting pass, and a final message claiming full test coverage. Unpack should flag the untested async path and the unsupported claim.

## 3. Architecture

```
Developer machine                 Unpack server (docker compose)
-----------------                 ------------------------------
git push ──► pre-push hook  ───►  API (FastAPI)  ──► Postgres (state, jobs)
             (find session,        /v1/ingest          │
              trim, redact,        /api/*, /a/*        ▼
              send)                     │          Worker
                                        │          analyze_push ─► code graph (in-process)
GitHub ◄── PR comment (App) ◄───────────┤          reasoning (Gemini; placeholder today)
                                        │          reconciler (every 30 s)
Reviewer browser ───────────────────────┘          render_image (Chromium)
```

The full architecture, including the public tunnel and the external services, is in [server design §1](server-design.md#1-architecture).

## 4. Components

Unpack has six parts. Each can be built and replaced on its own. The status column reflects `main` at `7ad132c`.

| # | Component | Buildathon intent | Status on main | Design doc |
|---|---|---|---|---|
| 1 | CLI and hook | On push: find the session, remove secrets, send session, diff and session ID | **Built.** Real hook, session trimming, secret scanning, ingest transport | [cli-hook.md](cli-hook.md) |
| 2 | Server | Receive, queue, store, serve live pages | **Built** (API, queue, worker, reconciler, comments, render, login) | [server-design.md](server-design.md) |
| 3 | AI processing | Per-function reasons from the session, with evidence and session review | **Not built.** Placeholder returns no reasons; session turns are not parsed | [session-pipeline.md](session-pipeline.md) |
| 4 | Code knowledge graph | Tree-sitter graph of the repo, updated per change | **Built** as `unpack_graph/` (Python only). Tree-sitter for pass 1; storage is in-process, not Neo4j | [graph-design.md](graph-design.md) |
| 5 | PR comment | One comment per PR, edited in place, summary, flags, image, live link | **Built** (text and image publishing, marker-based update) | [server-design.md §8](server-design.md#8-github-app-and-the-pr-comment) |
| 6 | Interactive graph | React and Sigma.js graph per PR and commit with a properties panel | **Stub.** `web/` has one placeholder page; the UI packages are declared but unused | [ui-design.md](ui-design.md) |

### 4.1 CLI and hook (developer's machine)

A command-line tool that installs a git hook. On push, it finds the agent session that produced the change, removes secrets locally, and sends the session, the diff and the session ID to the server. The hook never blocks a push.

Intent from the plan: a TypeScript or Go binary with gitleaks-style scanning. **Built instead** in Python, as `cli/`, with a `unpack` entry point. See [cli-hook.md](cli-hook.md).

Commit trailers (`Unpack-Session: <id>`) were proposed to link sessions to commits. **Deferred:** the demo matches one session per push, and the trailer is listed as later work in the session pipeline.

### 4.2 Server (receives and stores)

An API that receives what the CLI sends, queues it, stores the results and serves the live graph pages. It runs as Unpack's hosted service, or inside a customer's own cloud.

The plan recommended Node or FastAPI and Postgres. **Built:** FastAPI, SQLAlchemy and Alembic, Postgres 16, and a Postgres job queue (`SELECT … FOR UPDATE SKIP LOCKED`). The base URL is configurable through `UNPACK_BASE_URL`.

### 4.3 AI processing (inside the server)

Turns a long session into short reasons. It reads the edit steps, maps each edit to the function it changed, and asks the model to explain each change using only the turns that led up to it.

- Model: Gemini through Google AI Studio (buildathon) or Vertex AI (self-hosted), with structured JSON output. Current model names are in [server design §7.3](server-design.md#73-models).
- **Every reason links back to the session turns it came from.** When the session gives no reason, Unpack says so rather than guessing.
- Reasoning is stored permanently and never regenerated.

**Status:** not built. The pipeline design is in [session-pipeline.md](session-pipeline.md).

### 4.4 Code knowledge graph (per repository)

Files, functions, classes and tests as nodes; calls, imports and "test covers" as edges. Built once per repository, then updated per change by re-parsing only the files that changed.

Built as `unpack_graph/`. Calls carry a confidence tier (`EXTRACTED`, `INFERRED`, `AMBIGUOUS`), and reachability labels say which functions no test reaches. Start language: Python. Commit-by-commit history is later work.

### 4.5 Pull request comment

One comment per pull request, edited in place on every push. It holds the summary, flags such as "2 changed functions have no tests", a static image of the changed region and a link to the live graph. Built as a GitHub App (see [server design §8](server-design.md#8-github-app-and-the-pr-comment)). The Mermaid fallback for self-hosted customers is cut for the buildathon.

### 4.6 Interactive graph (the live view)

A web page per pull request or commit: the changed region (changed functions, one hop out and their tests), a panel with each node's properties (callers, callees, tests, reason, evidence), and a commit picker. The design uses React Flow for the PR view and Sigma.js with Graphology for the codebase map, not Sigma alone. See [ui-design.md](ui-design.md).

The server generates the analysis when the analysis finishes and stores it. The link itself never expires. Access requires GitHub login and repository access, and the server checks that before showing anything.

## 5. Works with any agent

Unpack must work with Claude Code, Cursor, Kiro, Gemini CLI, Codex, GitHub Copilot and future agents. Everything agent-specific stays in one thin layer.

- **One adapter per agent.** Each adapter knows where that agent stores its sessions and how to read them.
- **One common session format.** Adapters convert each session into one Unpack format: messages, tool calls, file edits with line ranges, timestamps and model name.
- **Read existing standards too.** Entire, Git AI and Agent Trace sessions can be accepted later.
- **Fall back gracefully.** Without a session, use the linked ticket and PR description, and show where the reasoning came from.

For the buildathon, one adapter exists: **Gemini CLI**. The server parses that format into a common internal type (`UnpackSession`) that later adapters must produce as well. The common format is not on the wire yet.

## 6. Scope and recommendations

- **Scope:** one agent (Gemini CLI), one language (Python), GitHub only.
- **Measure the win.** Time how long it takes to understand 5 to 10 real agent pull requests with and without Unpack. One number, such as "11 minutes to 2", carries the pitch.
- **Never show a reason without evidence.** A confident but wrong "why" is worse than none.
- **Lead with the reasoning, not the visuals.** Graph views are easy to copy; accurate per-function reasoning on a real code graph is not.
- **Watch similar tools.** code-nexus combines a code graph with git history; GitNexus has a strong graph UI to learn from. Its licence does not allow reusing its code commercially.
- **Keep privacy in mind.** Clean secrets before anything leaves the machine, and keep transcript quotes behind the authenticated link, not in the pull request.
- **Build the code graph from scratch,** on your own time and equipment, and check your employment contract's IP terms.

**Later, beyond the buildathon:** commit-by-commit history of the graph, a pre-merge preview of how a change reshapes the codebase, an MCP so agents can query reasons and history, and checks of the agent's claims against CI results.

**Business model:** free for individual developers running locally; a paid hosted service; and a paid annual licence for companies that self-host inside their own cloud and use their own model access.

## 7. Changes since the first plan

| Topic | First plan | Current decision | Why |
|---|---|---|---|
| Graph storage | Neo4j | In-process graph, pickled per commit under `DATA_DIR/graphs`. Neo4j is not in `docker-compose.yml`; `unpack_graph/neo4j_io.py` stays as an optional loader | Fewer moving parts for the demo; the map and node endpoints are served from the cached graph |
| When the graph view is built | On first open, cached about 24 h | Built during analysis and stored. Only the codebase map cache is about 24 h | The PR image needs the same data at analysis time |
| Frontend libraries | Sigma.js and Graphology for everything | React Flow for the PR view (cards with text), Sigma.js for the codebase map only | Sigma cannot draw text cards; see [ui-design.md §2](ui-design.md#2-re-evaluating-the-stack) |
| Session link | Commit trailer | Deferred. One session per push, matched by the hook | Trailer linking is later work in the session pipeline |
| Agent for the first adapter | Claude Code or Gemini CLI | Gemini CLI | The demo session is recorded there |
| LLM temperature | 0 (pipeline draft) | Model default (Gemini 3 advises against changing it) | [server design §7.4](server-design.md#74-request) |
| Ingest endpoint | `{server}/ingest` (pipeline draft) | `POST /v1/ingest` | [server design §5.1](server-design.md#51-post-v1ingest-cli-hook) |
| Mermaid fallback | Planned for self-hosted | Cut for the buildathon | Not needed for the demo |

Open decisions are listed in [status.md §4](status.md#4-open-decisions).
