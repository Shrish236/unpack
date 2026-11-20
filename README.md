# 🧭 Unpack

> **Turns AI-written code changes into an explained, explorable graph.**

Unpack helps engineering teams understand code they did not write themselves. For every pull request an AI agent produces, Unpack extracts the reasoning behind each changed function, backs every claim with verbatim evidence from the agent's session, flags untested code paths, and renders an interactive knowledge graph instead of an overwhelming diff.

---

## 🎯 The Problem

Code comprehension is the modern software bottleneck. AI coding agents write code far faster than humans can review, comprehend, and verify. When reviewers, on-call engineers, or incident responders look at an AI-generated pull request:
- They don't know **why** a specific line or function was changed.
- They cannot tell if the agent fulfilled what the user asked or went down an unverified tangent.
- They cannot easily see what calls into the change or which code paths lack test coverage.

Unpack closes this gap by bridging the agent session with the repository's code knowledge graph.

---

## 🏛 Architecture

```
Developer + Agent (Gemini CLI, Claude Code, Cursor)
       │
       ▼ (git push)
  pre-push hook (CLI)
  • Scans & scrubs secrets locally (.env, tokens)
  • Captures session turns & diff
  • Gzips & streams to Unpack server
       │
       ▼
 ┌─────────────────────────────────────────────────────────────┐
 │                      Unpack Server                          │
 │                                                             │
 │  ┌─────────────────┐    ┌────────────────────────────────┐  │
 │  │ API (FastAPI)   │    │ Background Worker              │  │
 │  │ • Ingestion API │    │ • Analyze push jobs            │  │
 │  │ • OAuth & Auth  │    │ • Branch reconciler loop       │  │
 │  │ • Static Web UI │    │ • Playwright screenshot render │  │
 │  └────────┬────────┘    └──────────────┬─────────────────┘  │
 │           │                            │                    │
 │    ┌──────▼────────┐           ┌───────▼────────┐           │
 │    │  Postgres 16  │           │    Neo4j 5     │           │
 │    │ State & Jobs  │           │ Code Knowledge │           │
 │    └───────────────┘           └───────┬────────┘           │
 │                                        │                    │
 │  ┌─────────────────────────────────────▼─────────────────┐  │
 │  │ Gemini AI Reasoning Engine (Google GenAI)             │  │
 │  │ • Explains per-function rationale                     │  │
 │  │ • Classifies drivers (user_asked vs agent_decided)    │  │
 │  │ • Verbatim quote verification against session turns   │  │
 │  └───────────────────────────────────────────────────────┘  │
 └──────────────────────────────┬──────────────────────────────┘
                                │
          ┌─────────────────────┴─────────────────────┐
          ▼                                           ▼
   Pull Request Comment                         Interactive UI
   • Summary & test gap warnings                • React Flow (PR cards view)
   • Linked static preview image                • Sigma.js (Whole codebase map)
   • Link to interactive graph                  • Session timeline & Why tab
```

---

## 🧩 The 6 Core Components

1. **CLI & Git Hook (`cli/`)**:
   - Installed via `unpack install --server <URL> --token <TOKEN>`.
   - On `git push`, scrubs secrets locally using regex and `.env` dictionaries, captures the agent session from `~/.gemini/tmp/`, and sends the diff and session payload to the server.
2. **Server (`server/`)**:
   - High-throughput FastAPI API + background job worker.
   - Postgres job queue (`SELECT ... FOR UPDATE SKIP LOCKED`).
   - Branch reconciler that tracks pushed branches, discovers pull requests, and updates PR comments idempotently.
3. **AI Reasoning Engine (`server/app/llm/` & `server/app/pipeline/`)**:
   - Built on `google-genai` SDK with Gemini 3 Pro / 2.5 Pro.
   - Structured JSON output mapping changes to reasons, driver origin, and history.
   - Rigorous verification checking every quote verbatim against session turns.
4. **Code Knowledge Graph (`unpack_graph/`)**:
   - Tree-sitter and AST two-pass parser.
   - Call graph resolution with confidence tiers on every edge (`EXTRACTED`, `INFERRED`, `AMBIGUOUS`). Calls that cannot be resolved are kept on their function with the reason, not as edges.
   - Argument-gated BFS test reachability with the labels `direct`, `reached`, `reached_uncertain` and `none`. `none` is the only red flag, and it is checked against a real coverage run (`unpack-graph coverage-check`).
   - Function-level change classification (text only, signature, behaviour) and the GraphView region for a change.
   - Neo4j persistence, a single-query region, and incremental updates.
5. **PR Comment Bot (`server/app/github/`)**:
   - GitHub App integration editing a single comment per PR on every push.
   - Includes change summary, risk flags (e.g. untested functions), rendered graph screenshot, and authenticated live link.
6. **Interactive Graph UI (`web/`)**:
   - **PR View**: Built with React 19 and `@xyflow/react` (React Flow) with ELK compound layout for crisp cards, test paths, and reasoning details.
   - **Codebase Map**: Built with `sigma` v3 and `graphology` with deterministic d3 circle-packing for repository context.

---

## 📁 Repository Layout

```
unpack/
├── README.md                      # Project documentation
├── pyproject.toml                 # Python packaging and dependencies
├── docker-compose.yml             # Postgres, Neo4j, API, Worker, Cloudflared
├── .env.example                   # Environment configuration template
├── Makefile                       # Development task shortcuts
├── docs/
│   └── graph-design.md            # Design, tiers, validation, adapting to other repositories
├── schemas/
│   └── graphview.schema.json      # Stable JSON schema for GraphView
├── unpack_graph/                  # Code knowledge graph library & CLI
│   ├── model.py                   # Data models (Shape, CallSite, FuncInfo, ModuleInfo, ...)
│   ├── extract.py                 # Pass 1: Syntax extraction & hashing
│   ├── resolve.py                 # Pass 2: Whole-repo symbol & call resolution
│   ├── graph.py                   # In-memory graph container & builder
│   ├── reach.py                   # Test reachability BFS with argument gating
│   ├── diff.py                    # Change detection & classification
│   ├── region.py                  # GraphView region builder
│   ├── incremental.py             # Incremental graph update
│   ├── neo4j_io.py                # Neo4j loader and Cypher queries
│   ├── source.py                  # FsSource and GitSource abstractions
│   ├── evaluate.py                # Measurements: coverage against ast, coverage check
│   └── cli.py                     # `unpack-graph` CLI
├── server/                        # FastAPI server & worker
│   ├── Dockerfile                 # Multi-stage production container
│   └── app/
│       ├── main.py                # FastAPI entrypoint & static mount
│       ├── config.py              # Pydantic-settings configuration
│       ├── db.py, models.py       # SQLAlchemy ORM models
│       ├── schemas/api.py         # Master API & UI JSON contract
│       ├── routers/               # Ingest, Live, Webhook, Auth, Admin
│       ├── github/                # GitHub App client, comments, PR tracking
│       ├── pipeline/              # Session parsing, edit mapping, verification
│       ├── llm/                   # Gemini client, structured output, prompts
│       └── jobs/                  # Worker loop, queue, reconciler, render
├── cli/                           # Developer CLI tool & pre-push hook
│   ├── main.py                    # `unpack` CLI commands
│   ├── hook.py                    # Pre-push hook runner
│   ├── secrets.py                 # Local secret scrubbing engine
│   └── session_finder.py          # Gemini CLI session finder
├── contract/                      # Schema sync & test fixtures
│   ├── export_schemas.py          # Exports Pydantic schemas to JSON Schema
│   ├── schema/                    # Generated JSON schemas for UI
│   └── fixtures/                  # Demo scenarios (e.g. analysis_done.json)
├── web/                           # React 19 + TypeScript + Vite frontend
│   ├── package.json
│   ├── vite.config.ts
│   └── src/                       # PR view, Codebase map, Timeline, Detail panel
└── tests/                         # Test suite
    ├── test_extraction.py         # Pass 1 corner cases, checked against ast
    ├── test_resolution.py         # Pass 2: imports, types, dispatch, containers
    ├── test_reachability.py       # Test reachability and argument gating
    ├── test_dynamic_dispatch.py   # getattr-dispatched methods
    ├── test_diff.py               # Change classification and the region schema
    ├── test_neo4j.py              # Neo4j parity and delta (needs the neo4j service)
    ├── test_incremental.py        # Incremental update equals a full rebuild
    ├── test_evaluate.py           # Measurements and the coverage check
    └── fixtures/                  # Small Python packages the graph tests analyse
```

---

## 🚀 Quickstart & Development

### 1. Prerequisites
- **Python**: `>= 3.11`
- **Node.js**: `>= 20.0.0`
- **Docker & Docker Compose** (for Postgres & Neo4j)

### 2. Clone & Configure
```bash
git clone https://github.com/Shrish236/unpack.git
cd unpack

cp .env.example .env
# Edit .env and supply your GEMINI_API_KEY
```

### 3. Start Database Services
```bash
docker compose up -d postgres neo4j
```

### 4. Install Dependencies
```bash
# Install Python packages in editable mode
pip install -e ".[dev]"

# Install Web dependencies
cd web && npm install && cd ..
```

### 5. Export Schemas & Run Tests
```bash
# Export Pydantic models to JSON schemas for the frontend
python contract/export_schemas.py

# Run test suite (the Neo4j tests need `docker compose up -d neo4j`;
# without it they are skipped, and with it they clear the database they use)
pytest
```

### 6. Run the Application
In separate terminals:
```bash
# Start FastAPI backend server (http://localhost:8000)
uvicorn server.app.main:app --reload --port 8000

# Start background worker & reconciler
python -m server.app.jobs.worker

# Start frontend development server (http://localhost:5173)
cd web && npm run dev
```

---

## 🛠 CLI Usage

### Build Code Knowledge Graph
```bash
# Pass 1 only: check every definition against Python's ast module
unpack-graph extract . --check-ast

# Call graph with a confidence tier per edge, and reachability labels
unpack-graph build .
unpack-graph build . --neo4j                       # also load into Neo4j

# Functions changed between two revisions, classified
unpack-graph changed . main feature-branch --json

# GraphView region JSON for the change (schemas/graphview.schema.json)
unpack-graph region . main feature-branch --out region.json
unpack-graph region . main feature-branch --neo4j  # answered by the Cypher region query

# Measurements, and the reachability check against a real test run
unpack-graph eval .
coverage run -m pytest && coverage json -o cov.json   # run from the repository root
unpack-graph coverage-check . cov.json             # exits 1 on any false "none"
```

Neo4j connection: `UNPACK_NEO4J_URI`, `UNPACK_NEO4J_USER`, `UNPACK_NEO4J_PASSWORD` (defaults: `bolt://localhost:7687`, `neo4j`, `unpackpass` as in `docker-compose.yml`). Start the service with `docker compose up -d neo4j`.

The design, the tiers, the validation and how to adapt the graph to another repository are described in [docs/graph-design.md](docs/graph-design.md).

### Install Git Pre-Push Hook
In any project repository:
```bash
unpack install --server "https://unpack.yourdomain.com" --token "unp_your_repo_token"
```

---

## 📜 License
MIT License.
