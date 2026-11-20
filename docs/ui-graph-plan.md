# PR graph: build plan and decisions

Status: **plan.** Nothing in this document is built yet. `web/` on `main` is a placeholder page that does not compile (see §2.3).

This is the build plan for the **PR graph**: the interactive graph of one analysis, opened from the server dashboard. It narrows [ui-design.md](ui-design.md) to the piece being built now and records every decision taken for it (§3). Where this plan and `ui-design.md` disagree, this plan wins for the graph page, and the disagreement is listed in §3.6.

Written against `main` at `e4d0aa9` on 2026-11-20.

## Contents

1. [Scope](#1-scope)
2. [What the repository gives us today](#2-what-the-repository-gives-us-today)
3. [Decisions](#3-decisions)
4. [How the dashboard opens the graph](#4-how-the-dashboard-opens-the-graph)
5. [The page](#5-the-page)
6. [From API data to the canvas](#6-from-api-data-to-the-canvas)
7. [Layout](#7-layout)
8. [Node and edge components](#8-node-and-edge-components)
9. [Interactions](#9-interactions)
10. [Semantic zoom](#10-semantic-zoom)
11. [Static mode (PR comment image)](#11-static-mode-pr-comment-image)
12. [States: loading, running, failed, no session, errors](#12-states-loading-running-failed-no-session-errors)
13. [Fixtures and mocks](#13-fixtures-and-mocks)
14. [Testing](#14-testing)
15. [Server changes this plan needs](#15-server-changes-this-plan-needs)
16. [File layout](#16-file-layout)
17. [Build order and estimates](#17-build-order-and-estimates)
18. [Done when](#18-done-when)
19. [Open questions](#19-open-questions)

---

## 1. Scope

**In scope**

- The graph page at `/a/{public_id}`: the React Flow canvas for one analysis, with file and class frames, changed cards, context cards, tests, deleted (ghost) cards, collapsed chips and styled edges.
- A thin page shell around the canvas: a header (repository, PR, commit, back to the dashboard), a legend, and a node inspector drawer (§5.3).
- Selection, test path, nearest tested function, blast radius, collapsed-chip expansion, semantic zoom.
- Static mode for the PR comment image (`/render/{public_id}?static=1`).
- The data layer the page needs: generated types, React Query, a zustand store, MSW fixtures.

**Out of scope (built elsewhere or later)**

| Piece | Where it lives |
|---|---|
| Dashboard: list of sessions, pushes and analyses, session info | **Server dashboard, built separately.** It opens this graph on click (§4) |
| Session transcript drawer, session timeline and replay | Dashboard holds session info. Not on the graph page in this build |
| Change list (left panel) and guided tour | Later. The inspector covers single-node reading for now |
| Full detail panel with Code, Callers, Tests, Imports tabs (`GET .../nodes/{id}`) | Later. Slot reserved in the page layout (§5.1) |
| Commit picker (`GET /api/prs/.../analyses`) | Later |
| Codebase map (Sigma, folder packing) | Later, separate view |

---

## 2. What the repository gives us today

### 2.1 The data

`GET /api/analyses/{public_id}` returns `AnalysisResponse` (`server/app/schemas/api.py:283`, contract in [api-contract.md §5.2](api-contract.md#52-get-apianalysespublic_id)). The graph reads:

| Field | Used for |
|---|---|
| `graph.nodes[]` | Every card and frame. `kind` (file, class, function, method, test), `layer` (container, changed, neighbor, test, ghost), `parent`, `signature`, `start_line`, `change`, `test`, `callers_count`, `callees_count`, `finding_ids`, `imports`, `imports_total`, `bases`, `is_async`, `is_public` |
| `graph.edges[]` | Arrows. `kind` and `tier` |
| `graph.collapsed[]` | Chips such as "+12 callers in `_api.py`" |
| `graph.truncated` | "+N more not shown" notice |
| `reasons[node_id]` | Driver chip, one-line reason, inspector |
| `findings[]` | ⚠ count colour and inspector findings |
| `impact.by_node`, `impact.summary` | Blast radius |
| `reading_order` | Initial focus; order of changed cards inside a frame |
| `diff_hunks[node_id]` | Inspector "diff" section |
| `analysis`, `pull_request`, `banner`, `stats`, `summary` | Header and banners |

### 2.2 What the server actually sends (checked in `server/app/pipeline/graph_view.py`)

- **Caps:** at most 200 nodes, 500 edges, 15 neighbours per node (`server/app/config.py:65`). Overflow becomes `collapsed` groups. This is comfortably inside React Flow's range.
- **Layers emitted:** `container`, `changed`, `ghost`, `neighbor`, `test`. The schema also allows `impact`, but the builder never emits it.
- **Edge kinds emitted:** `CALLS` and `REACHES` only. `INHERITS`, `OVERRIDES` and `IMPORTS` are in the schema but never sent.
- **`REACHES` edges** go from the first test in `test.shortest_path` straight to the changed function (one edge, not the whole path).
- **`diff_hunks`** is keyed by **node ID** (`live.py:276`, `graph_view.py:382`). `api-contract.md §5.2` says "file path"; the code wins.
- **`reasons`, `findings`, `timeline`** are empty on real data today, because the session reasoning step is a placeholder ([status.md §2](status.md#2-what-is-built-placeholder-and-missing)). The banner is `reasons_unavailable` or `no_session`.
- **`history`** is already `list[{turn, text}]` in `api.py` (status O1 is settled in code; `ui-design.md §3.4` still calls it open).

### 2.3 The web app

- `web/src/App.tsx` is a placeholder and fails `tsc` with TS6133 (unused `React` import). The Dockerfile hides this with `npm run build || … touch dist/index.html`.
- No lockfile; `npm ci` cannot run.
- Packages already declared: `@xyflow/react` 12, `elkjs` 0.9, `zustand` 4, `@tanstack/react-query` 5, `shiki` 1, `msw` 2, `lucide-react`, React 19, Vite 5. Not declared: `json-schema-to-typescript`, `vitest`, `react-router`, `@testing-library/react`, `playwright`.
- Vite dev proxy for `/api`, `/auth`, `/img` → `localhost:8000` exists.
- The server's CSP already allows `worker-src 'self' blob:` and `style-src 'self' 'unsafe-inline'` (`server/app/main.py:21`), which React Flow and an ELK worker need. Status O3 is therefore satisfied on paper; it still needs a browser check (§14).

### 2.4 The fixture

`contract/fixtures/analysis_done.json` is the only fixture. It is too thin for the graph and is **not internally consistent**:

- 5 nodes: one file, two classes, two changed methods. No context cards, tests, ghosts or collapsed groups.
- Edges `e1` and `e2` start at `Client.send` and `AsyncClient.send`, which are not nodes.
- `impact.by_node` lists `AsyncClient.send` and `AsyncClient.request`, which are neither nodes nor in a collapsed group. `validate_graph_view` (`graph_view.py:444`) would reject this.
- `reading_order` starts with `httpx/_config.py::Retry.__init__`, which is not a node.

The UI must tolerate this (§6.4), and a new consistent fixture is written for development (§13).

### 2.5 The render path has a blocker

The renderer loads `/render/{public_id}?static=1&render_token=…` in Chromium with no cookie (`server/app/jobs/render.py:80`). The page then has to read `GET /api/analyses/{public_id}`, which requires a logged-in viewer (`Depends(viewer)`, `live.py:140`). In render mode that call returns **401**, so the image can never be produced once the UI fetches data. The current image "works" only because the stub page sets `data-ready` without fetching anything. Fix in §15.

---

## 3. Decisions

Each decision has an ID (`G1`, `G2`, …) so code comments and reviews can point at it. **Status** is one of:

- **Confirmed**: stated by the project owner.
- **Proposed**: my default; build proceeds on it unless changed. Listed again in §19 where a confirmation is needed.
- **Inherited**: already decided in `ui-design.md`, `server-design.md` or the code; restated here so this document is complete.

### 3.1 Scope and integration

| ID | Decision | Alternatives considered | Why | Status |
|---|---|---|---|---|
| G1 | Build only the graph now; the opening dashboard is built separately | Build the whole PR view | Owner's call | **Confirmed** |
| G2 | The server dashboard holds session info; clicking an analysis in the dashboard opens this graph | Graph page shows session info itself | Owner's call | **Confirmed** |
| G3 | The graph is its own page at `/a/{public_id}`, reached by an ordinary link from the dashboard | Embed the graph as a component inside the dashboard; open in a modal | The route already exists on the server (`images.py:58`), the login redirect only accepts `/a/…` paths (`auth.py:30`), the PR comment already links there, and the renderer uses the same app. One URL serves the dashboard click, the PR comment link and the image | Proposed |
| G4 | The dashboard opens the graph in the **same tab**; the graph header has a "← Dashboard" link back | New tab | Keeps browser history natural; the dashboard can still use `target="_blank"` if it prefers, nothing in the graph depends on it | Proposed |
| G5 | Deep links: `?node=<node_id>` preselects and centres a node; `?blast=1` opens with blast radius on; `?static=1` is static mode | Hash routes; state in local storage | Lets the dashboard open the graph on a specific function (e.g. a finding) and makes links shareable | Proposed |
| G6 | The graph page owns its own state in a zustand store (`useGraphStore`). The store is exported so a later detail panel, change list or an embedded dashboard can read and drive it (`select`, `focus`, `setBlastRadius`) | Props and callbacks only | One selection state is what `ui-design.md §2.2` asks for; a store avoids prop-drilling into React Flow node components | Proposed |
| G7 | The graph page fetches its own data by `public_id` (React Query). It does not receive the analysis from the dashboard | Dashboard passes the JSON via `postMessage` or storage | Works for direct links from the PR comment and the renderer, which have no dashboard | Proposed |
| G8 | Back-link target is `/` unless `VITE_DASHBOARD_URL` is set at build time | Hard-code a path | The dashboard's URL is not decided yet (§19) | Proposed |

### 3.2 Stack

| ID | Decision | Alternatives | Why | Status |
|---|---|---|---|---|
| G9 | React Flow (`@xyflow/react` 12) for the canvas | Sigma, Cytoscape, D3 | HTML cards with text; ≤ 200 nodes | Inherited (`ui-design §2.2`) |
| G10 | ELK (`elkjs`, `layered`) for layout, in a Web Worker | dagre; d3-force | Compound (nested) groups for file → class; deterministic | Inherited |
| G11 | zustand for UI state, React Query for fetching | Redux; context | Already declared | Inherited |
| G12 | TypeScript types generated from `contract/schema/*.json` with `json-schema-to-typescript` (`npm run types`); generated files committed under `web/src/api/generated/` | Hand-written types; openapi-typescript | `ui-design §2.5`; contract is already exported to JSON Schema. Committing the output means `npm run build` does not need Python | Proposed (commit the output) |
| G13 | Minimal routing without a router library: the page reads `location.pathname` (`/a/:id`, `/render/:id`) and `location.search` | `react-router` | Two routes, no navigation inside the app; one fewer dependency | Proposed |
| G14 | `lucide-react` for icons (kind, flask, warning, driver) | Emoji as in the design mock-ups | Emoji render differently in headless Chromium and can fail the image; icons are crisp in the PNG | Proposed |
| G15 | Styling with CSS variables and CSS modules; light and dark from `prefers-color-scheme`; static mode always light | Tailwind; CSS-in-JS | `ui-design §2.5`; no runtime styling cost | Inherited (static-light is Proposed) |
| G16 | Fonts bundled (e.g. Inter + JetBrains Mono as `.woff2` in `web/src/assets`), no Google Fonts | System fonts; CDN | CSP is `default-src 'self'`, `font-src 'self' data:`; identical text metrics in the renderer and the browser, which ELK sizing depends on | Proposed |
| G17 | Add dev dependencies: `vitest`, `@testing-library/react`, `jsdom`, `json-schema-to-typescript`; commit `package-lock.json` | No tests | Status §8 lists the missing lockfile; tests are needed for §14 | Proposed |
| G18 | Shiki is **not** used in this build; the inspector shows the diff hunk as preformatted text with `+`/`-` line colouring | Load Shiki now | Code tab is out of scope (§1); keeps the bundle small. Shiki comes with the detail panel | Proposed |

### 3.3 Mapping and layout

| ID | Decision | Alternatives | Why | Status |
|---|---|---|---|---|
| G19 | Nesting follows `parent`: file frame → class frame → card. Nodes whose parent is not in the payload attach to a synthetic file frame built from `path` | Flat graph | `ui-design §3.1`; robust to partial payloads | Inherited + Proposed (synthetic frame) |
| G20 | Node type per node: `layer=container,kind=file` → `fileFrame`; `layer=container,kind=class` → `classFrame`; `layer=changed` → `changedCard`; `layer=ghost` → `ghostCard`; `layer=test` or `kind=test` → `testPill`; `layer=neighbor` (and anything else) → `contextCard`; each `collapsed` group → `collapsedChip` | Choose by `kind` alone | `layer` is what the server uses to say why a node is present | Proposed |
| G21 | Layout direction **top to bottom**: callers above, changed cards in the middle, callees and tests below (`elk.direction: DOWN`) | Left to right | A call chain reads downward; fits the 1200 × 700 image better than a wide row | Proposed (owner asked; not yet answered) |
| G22 | Fixed card sizes per node type, used both by ELK and by the components: changed 264 × 116, context 208 × 48, test pill 200 × 32, ghost 240 × 72, chip 180 × 32. Frames are sized by ELK | Measure the DOM then lay out | No measure pass, so layout runs once in the worker and zoom never triggers re-layout; text is truncated with an ellipsis and full text is in the inspector | Proposed |
| G23 | Layout runs in a Web Worker created by Vite (`new Worker(new URL(...), {type: 'module'})`), falls back to the main thread if worker creation fails | Main thread only | Keeps the page responsive; CSP already allows `worker-src 'self' blob:` | Proposed |
| G24 | Layout is computed once per analysis and again only when the set of visible nodes changes (chip expanded, test-path nodes added). Positions of already-placed nodes are kept stable by passing them as ELK `interactive` hints | Re-layout on every change | Avoids the graph jumping when the user expands a chip | Proposed |
| G25 | Within a frame, changed cards are ordered by `reading_order`, then by `start_line` | Alphabetical | Matches how the change should be read | Proposed |
| G26 | Collapsed chips sit inside the frame of `collapsed.file` if that frame is on the canvas, otherwise in a synthetic frame for that file; they connect to `anchor` with a faint edge in the chip's direction (callers above, callees/tests below) | Always next to the anchor | Keeps "where" visible: "+12 callers in `_api.py`" is in `_api.py` | Proposed |
| G27 | Edges between nodes inside different frames are routed by ELK across hierarchy (`hierarchyHandling: INCLUDE_CHILDREN`) | Per-frame layouts | Needed for clean cross-file arrows | Proposed |

### 3.4 Visual encoding

| ID | Decision | Status |
|---|---|---|
| G28 | Change stripe and badge: `added` green "ADDED"; `functional` amber "MODIFIED"; `signature` amber "SIGNATURE"; `text_only` grey "FORMATTING" with a muted card; `deleted` ghost card (dashed border, struck-through name, "Removed · still called by N" from `callers_count`) | Inherited (`ui-design §3.2`); server uses `functional` for "modified" |
| G29 | `change.source = outside_session` adds an "outside session" badge; the reason line reads "Not from the session". `session_then_formatted` and `session_partial` show a small "partly from session" marker | Inherited + Proposed (marker for the two partial sources) |
| G30 | Test status on the card footer: `direct` green flask "tested"; `reached` green flask "reached (N)"; `reached_uncertain` amber flask "maybe reached"; `none` red flask "no test" **and** a red card outline | Inherited; labels Proposed |
| G31 | Findings: ⚠ with the count of `finding_ids`; colour by kind: `claim_not_backed`, `test_failed_ignored`, `request_not_done`, `check_weakened` red; `not_tested_after_change`, `dead_end` amber | Proposed (the contract has no severity field) |
| G32 | Driver chip: `user_asked` "User asked", `agent_decided` "Agent decided", `not_stated` "Not stated"; no chip when there is no reason | Inherited |
| G33 | When `reasons[id]` is missing, the card shows "No reason found in the session" in muted text, and the page shows the `banner` message at the top | Inherited (`ui-design §3.4`) |
| G34 | Edges: `CALLS`+`EXTRACTED` solid arrow; `CALLS`+`INFERRED` dashed; `CALLS`+`AMBIGUOUS` dotted and faint; `REACHES` thin green, **hidden until** its target is selected; chip edges faint grey | Inherited |
| G35 | Import edges are **not drawn** (the server sends none). The file frame header shows "imports N ▾" from `imports_total`, expanding to the `imports` list | Proposed (design asked for hover edges; data does not allow it) |
| G36 | Class frames show `bases` as "extends A, B" in the header | Inherited |
| G37 | Async functions show an "async" tag; non-public (`is_public=false`) names are shown in a lighter weight | Proposed |
| G38 | Colours are CSS variables with light and dark values; change colours keep a 4.5:1 text contrast in both themes | Proposed |

### 3.5 Interaction

| ID | Decision | Status |
|---|---|---|
| G39 | Click selects a node; Esc or a click on empty canvas clears it. Selection dims everything not connected to it (opacity 0.25) and brightens its edges | Proposed |
| G40 | On first load, the first changed node in `reading_order` that exists on the canvas is centred (not selected), unless `?node=` is given | Proposed |
| G41 | Selecting a changed node with `test.shortest_path` highlights the path in green. Path steps not on the canvas are added as compact context cards and the layout updates (G24) | Inherited (`ui-design §3.6`) |
| G42 | Selecting a node with `test.label = none` shows "No test reaches this" in the inspector and outlines `test.nearest_tested` (centring it if on the canvas, else naming it in the inspector) | Inherited |
| G43 | Blast radius toggle (button and key **B**). Uses `impact.by_node` of the selected node, or of all changed nodes when nothing is selected. Depth 1/2/3 coloured strong → faint; `uncertain` hops and `INFERRED`/`AMBIGUOUS` tiers drawn faint and labelled "uncertain". Hops not on the canvas add their count to the matching collapsed chip ("+7 in `_api.py` · 3 affected"). `impact.summary` shows in a small overlay: "Reaches 23 functions in 6 files; 4 public API; 2 paths uncertain" | Inherited (`ui-design §3.5`); chip counting Proposed |
| G44 | Clicking a collapsed chip expands it into compact context cards built from `node_ids` (label from the part after `::`, path from the part before). They have no counts until the detail endpoint is used. A second click collapses | Proposed |
| G45 | Hover shows a tooltip with the full name, path:line and signature (for truncated text) | Proposed |
| G46 | Node dragging is off; pan and zoom are on; the React Flow mini-map is on in live mode, off in static mode | Proposed |
| G47 | Keyboard: arrow keys move selection along `reading_order` (← →); **B** blast radius; **F** fit view; **/** focus the search box (filters cards by name, highlights matches) | Proposed (search is the cheap version of `ui-design §4.2`) |
| G48 | `onlyRenderVisibleElements` on; node components wrapped in `React.memo`; the store is read with selectors so a selection change re-renders only affected nodes | Proposed |

### 3.6 Where this plan differs from `ui-design.md`

| ID | `ui-design.md` says | This plan | Why |
|---|---|---|---|
| G49 | Three-column PR view: change list, canvas, detail panel; timeline at the bottom | Canvas plus header plus an inspector drawer | G1, G2: dashboard holds session info; only the graph is built now |
| G50 | Import edges on hover of a file header | Imports listed in the header, no edges | Server sends no `IMPORTS` edges (§2.2) |
| G51 | `history` timeline is an open conflict | `history` is `list[{turn, text}]`; inspector shows it as a vertical list | Already settled in `api.py` |
| G52 | Node kind `module` | `file` | Matches the server |
| G53 | Emoji in the card mock-ups | Icons (G14) | Rendering stability in the PNG |

### 3.7 Static image

| ID | Decision | Status |
|---|---|---|
| G54 | Static mode is the same page with `?static=1`: canvas only, no header controls, no inspector, no mini-map; a title strip (repo · PR #n · short sha) and a legend | Inherited (`ui-design §5`) |
| G55 | Viewport 1200 × 700 at 2×. Fit the view to changed and ghost cards plus their one-hop neighbours. If that does not fit at zoom ≥ 0.6, fit to changed cards only and show a "+N more in the live graph" chip | Inherited; the 0.6 threshold is Proposed |
| G56 | Static mode forces the "medium" zoom tier (G60) regardless of the actual zoom, light theme, and disables animations and transitions | Proposed |
| G57 | `document.body.dataset.ready = "true"` only after: data loaded, layout done, fonts loaded (`document.fonts.ready`), fit view applied, and two `requestAnimationFrame`s. Any failure sets `data-error` with a short message. No `console.error` on the happy path (the renderer fails on any) | Inherited (`server-design §9`); the exact sequence is Proposed |
| G58 | In static mode the page reads the analysis with the `render_token` from its own URL (needs the server change in §15.1) | Proposed |
| G59 | Live mode on `/a/{id}` also sets `data-ready` when drawn, so the same Playwright check covers both | Proposed |

### 3.8 Semantic zoom

| ID | Decision | Status |
|---|---|---|
| G60 | Three tiers from the React Flow zoom value: **far** < 0.55, **medium** 0.55–1.15, **close** > 1.15. Far: changed cards show name and change colour only; context cards hidden behind their chips. Medium: full card without the reason line. Close: full card with the reason line; context cards show the signature | Inherited (`ui-design §3.3`); thresholds Proposed |
| G61 | Card boxes keep the same size in every tier (contents change, not size), so zoom never triggers layout | Proposed (follows G22) |

### 3.9 Data handling

| ID | Decision | Status |
|---|---|---|
| G62 | `toFlow(analysis)` is a pure function with no React. It is the only place that interprets the contract, and it is unit-tested against every fixture | Proposed |
| G63 | Tolerant input: edges to unknown nodes are dropped (counted in a dev-only warning, not `console.error`); unknown `reading_order` ids are skipped; impact hops with no node and no chip are counted in the summary only. The page never crashes on a valid-schema payload | Proposed (driven by §2.4) |
| G64 | Polling: when `analysis.status` is `queued` or `running`, refetch every 3 s (matches `Retry-After: 3`), stop on `done` or `failed` | Proposed |
| G65 | A `401` from any `/api` call redirects to `/auth/login?next=<current path and query>`; `403 no_repo_access` and `404` show a full-page message with a link back to the dashboard | Inherited (`ui-design §6`) |
| G66 | Mocks: MSW serves fixtures at the real paths in development when `VITE_USE_MOCKS=true` (the default for `npm run dev`). `?fixture=<name>` picks the fixture. MSW is never in the production bundle (dynamic import guarded by `import.meta.env.DEV`) | Inherited (`ui-design §8.2`); bundle guard Proposed |

### 3.10 Process

| ID | Decision | Status |
|---|---|---|
| G67 | Work on branch `claude/ecstatic-thompson-oszc4e` | Inherited (session) |
| G68 | Fix the `App.tsx` build error first, then remove the Dockerfile fallback (`|| … touch dist/index.html`) once the graph page builds, so a broken UI fails the image build | Proposed (status §6, §8) |
| G69 | Contract changes go through `server/app/schemas/api.py` → `make contract` → regenerate types; the UI never adds fields of its own | Inherited (`ui-design §8.3`) |
| G70 | Fix `api-contract.md §5.2` to say `diff_hunks` is keyed by node ID, and correct `ui-design.md` on `history`, in the same change that adds the UI | Proposed |

---

## 4. How the dashboard opens the graph

```
Server dashboard (separate)                 Graph page (this plan)
───────────────────────────                 ──────────────────────
list of sessions / pushes / analyses
  │ each row has analysis.public_id
  │
  └─ click ──► /a/{public_id}                ──► GET /api/analyses/{public_id}
     (optional ?node=<id>, ?blast=1)              ├─ queued/running → "Analysing…" + poll 3 s
                                                  ├─ failed         → error message
                                                  └─ done           → graph
     "← Dashboard" ◄────────────────────────────── header link (G8)
```

**What the dashboard needs to provide:** only the link. The `public_id` is in `IngestResponse.analysis.public_id` and in every analysis the dashboard lists. Linking to a specific function: `/a/{public_id}?node=<url-encoded node id>`, for example `?node=httpx%2F_client.py%3A%3AAsyncClient._send_single_request`.

**Login:** the dashboard and the graph share the server's `unpack_session` cookie. If the viewer is not logged in, the graph page redirects to `/auth/login?next=/a/{public_id}…`, and `auth.py` returns the viewer to the same URL.

**What the graph does not do:** it does not read session info (turns, transcript) in this build. The inspector shows evidence quotes from `reasons[id].evidence` with their turn ids; a link "Open in dashboard" can point to the dashboard's session view once its URL scheme is known (§19).

---

## 5. The page

### 5.1 Layout (live mode)

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ ← Dashboard   encode/httpx · PR #12 Add retries… · a1b2c3d     [Blast radius B] [/]  │
│ banner (if any): "Reasons are not available for this analysis yet."                  │
├──────────────────────────────────────────────────────────────────┬───────────────────┤
│                                                                  │ Inspector (380px) │
│   GRAPH CANVAS (React Flow)                                      │ opens on select,  │
│                                                                  │ closes on Esc     │
│   ┌─ httpx/_client.py ── imports 14 ▾ ──────────────────────┐    │                   │
│   │ ┌ class Client ───────────┐  ┌ class AsyncClient ──────┐│    │                   │
│   │ │ [card] _send_single_req │  │ [card] _send_single… ⚠1 ││    │                   │
│   │ └─────────────────────────┘  └─────────────────────────┘│    │                   │
│   └─────────────────────────────────────────────────────────┘    │                   │
│        [+12 callers in _api.py]      [3 tests]                   │                   │
│                                                     ┌ minimap ┐  │                   │
│ legend ▾                         impact summary     └─────────┘  │                   │
└──────────────────────────────────────────────────────────────────┴───────────────────┘
```

The inspector is a drawer that overlays the right edge on narrow screens (< 1100 px) and docks on wide ones. The page layout leaves a left slot unused for the future change list.

### 5.2 Header

Repository (`analysis.repo.owner/name`), PR number and title (linked to `pull_request.url`, if present), short sha, branch. Controls: blast radius toggle, search, fit view, theme follows the system. A stats line: "6 functions changed · 1 not reached by tests · 1 finding" from `stats` and `findings`.

### 5.3 Inspector (minimal detail panel)

Built only from `AnalysisResponse`, no extra request:

1. Name, kind, `path:start_line`, signature, async/public tags, change badge and source.
2. **Why:** full `reason`, driver, confidence; `history` as a vertical list of `{turn, text}`; `evidence` as quote blocks with turn ids. "No reason found in the session" when absent.
3. **Findings** whose `functions` include this node, each with its evidence.
4. **Tests:** label, count, shortest path as a clickable list; or "No test reaches this" and the nearest tested function.
5. **Calls:** callers and callees **on the canvas** (from edges), plus "↑ N callers / ↓ N calls in total" from the counts.
6. **Blast radius** for this node from `impact.by_node`.
7. **Diff:** `diff_hunks[id]` as preformatted text (G18).

---

## 6. From API data to the canvas

### 6.1 `toFlow(analysis, view)` → `{nodes, edges, index}`

Inputs: the analysis and a `view` object (`expandedChips`, `extraNodes` from test paths). Output: React Flow nodes (with `parentId` and `extent: 'parent'` for nesting), edges, and an index used by highlighting (`byId`, `callersOf`, `calleesOf`, `chipsByAnchor`, `chipByMemberId`).

Steps:

1. Index `graph.nodes` by id.
2. Create frames for `container` nodes; create synthetic file frames for any `path` with no frame (G19).
3. Create cards per G20, set `parentId` to the class frame if `parent` is a class, otherwise to the file frame.
4. Create chips from `graph.collapsed` (G26), skipping groups whose chip is expanded; for expanded groups create context cards from `node_ids`.
5. Add `extraNodes` (test-path steps) as context cards in their file frames.
6. Create edges (G34), dropping ones with a missing end (G63). Add one faint edge per chip to its anchor.
7. Attach per-node display data: `reason`, `findings` (resolved from `finding_ids`), `impactDepth` (filled by the highlight step, not here).

### 6.2 Display data per changed card

```ts
type ChangedCardData = {
  id: string; name: string; kind: 'function' | 'method';
  path: string; line: number | null; signature: string | null;
  isAsync: boolean; isPublic: boolean;
  change: NodeChange;                    // kind + source
  reason: FunctionReason | null;         // from reasons[id]
  test: NodeTest | null;
  callers: number; callees: number;
  findings: { id: number; kind: ReviewFinding['kind'] }[];
};
```

### 6.3 Highlight state (computed, not stored in nodes)

`computeHighlight(index, store)` returns `{nodeEmphasis: Map<id, 'selected'|'neighbor'|'path'|'impact1'|'impact2'|'impact3'|'nearest'|'dim'>, edgeEmphasis: Map<id, …>}`. Node components read their own entry through a selector, so changing selection does not rebuild the node list.

### 6.4 Tolerance

Per G63. In development a single `console.warn` lists what was dropped; in production nothing is logged (the renderer treats `console.error` as failure, warnings are fine but kept out anyway).

---

## 7. Layout

ELK options (root):

```js
{
  'elk.algorithm': 'layered',
  'elk.direction': 'DOWN',                         // G21
  'elk.hierarchyHandling': 'INCLUDE_CHILDREN',     // G27
  'elk.layered.spacing.nodeNodeBetweenLayers': 48,
  'elk.spacing.nodeNode': 24,
  'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
  'elk.layered.crossingMinimization.semiInteractive': true,  // G24
  'elk.edgeRouting': 'ORTHOGONAL'
}
```

Frames: `elk.padding: [top=36 (header), left=12, bottom=12, right=12]`. Cards: fixed sizes (G22). Within a frame, `elk.layered.considerModelOrder.strategy: NODES_AND_EDGES` with children ordered per G25.

Worker protocol: `postMessage({id, graph})` → `{id, positions, sizes}` or `{id, error}`. Stale responses (older `id`) are ignored. Timeout 8 s → `data-error="layout timeout"` in static mode, a message in live mode.

Edges: drawn by React Flow (smooth step) between handles placed top (in) and bottom (out); ELK's routing is used only for node positions. This keeps edges simple to restyle on selection.

---

## 8. Node and edge components

| Component | Size | Content (medium tier) | Notes |
|---|---|---|---|
| `FileFrame` | ELK | Path; "imports N ▾" | Collapsible imports list; tinted when it contains changed cards |
| `ClassFrame` | ELK | `class Name` · "extends …" | |
| `ChangedCard` | 264 × 116 | Kind icon + name + badge · `path:line` · signature · driver chip · footer ↑ ↓ · test · ⚠ | Left stripe colour per G28; red outline per G30; reason line in close tier |
| `ContextCard` | 208 × 48 | Kind icon + name · file · ↑ ↓ | Signature in close tier |
| `TestPill` | 200 × 32 | Flask + test name | Green border if on the selected node's path |
| `GhostCard` | 240 × 72 | Struck-through name · "Removed · still called by N" | Dashed border |
| `CollapsedChip` | 180 × 32 | "+12 callers in `_api.py`" | Click to expand (G44); blast count when on (G43) |
| `CallEdge` | — | Arrow styled by tier | Label "uncertain" on faint edges when blast radius is on |
| `ReachesEdge` | — | Thin green | Visible only for the selected node |

Legend (live: collapsible bottom-left; static: fixed strip): change colours, test status, edge tiers.

---

## 9. Interactions

Summarised from G39–G48:

| Action | Result |
|---|---|
| Click a card | Select, open inspector, dim the rest, show its test path or nearest tested |
| Click empty canvas / Esc | Clear selection, close inspector |
| ← / → | Previous / next in `reading_order`, centring the card |
| B | Toggle blast radius |
| F | Fit view |
| / | Search box; matching cards highlighted, Enter centres the first |
| Click a chip | Expand into context cards; click again to collapse |
| Click a path step in the inspector | Select and centre that node |
| Load with `?node=` | Select and centre that node |

---

## 10. Semantic zoom

Per G60–G61. Implementation: `useStore(s => s.transform[2])` from React Flow mapped to a tier in a small hook; the tier is stored once in zustand so cards read it with a selector and re-render only when the tier changes, not on every zoom tick. Static mode pins the tier to `medium` (G56).

---

## 11. Static mode (PR comment image)

Sequence (G57):

1. Read `public_id` and `render_token` from the URL.
2. Fetch the analysis (with the token, §15.1). On failure: `data-error="fetch <status>"`.
3. If status is not `done`: `data-error="analysis <status>"`.
4. `toFlow` → layout in the worker. On failure: `data-error="layout"`.
5. Render; wait for `document.fonts.ready`; fit view per G55; wait two animation frames.
6. `document.body.dataset.ready = "true"`.

The page has no network requests after step 2, so the renderer's "request failed" check cannot trip on lazy assets (fonts and the worker are bundled and loaded before step 5).

---

## 12. States: loading, running, failed, no session, errors

| State | Live page | Static page |
|---|---|---|
| Loading | Skeleton frame | Nothing until ready |
| `queued` / `running` | "Analysing this push…" with spinner; polls every 3 s (G64) | `data-error` (the server only renders done analyses) |
| `failed` | `error_code` and `error_message`, link back | `data-error` |
| `done`, `banner.kind = no_session` | Graph; banner "No agent session was sent with this push"; cards show no reason line | Graph; banner text in the title strip |
| `done`, `reasons_unavailable` | Graph; banner; "No reason found in the session" on cards | Same |
| `done`, `partial_coverage` / `out_of_date` | Graph with the banner | Same |
| `done`, no changed functions | "No function-level changes in this push" | Same text, then `data-ready` |
| `graph.truncated` non-zero | "+N nodes not shown" notice | Same |
| 401 | Redirect to login (G65) | `data-error` |
| 403 / 404 | Full-page message | `data-error` |

---

## 13. Fixtures and mocks

New files in `contract/fixtures/` (hand-written to the schema, G69):

| Fixture | Contents |
|---|---|
| `analysis_graph_rich.json` | **Main development fixture.** Two files and one class each; changed cards of every kind (`added`, `functional`, `signature`, `text_only`) and one `deleted` ghost; one `outside_session` change; context neighbours (callers and callees, `EXTRACTED`, `INFERRED`, `AMBIGUOUS` edges); two tests with `REACHES` edges; one `none` node with `nearest_tested`; collapsed callers and tests; `impact.by_node` with depths 1–3 and an uncertain hop; reasons for some nodes, not others; two findings; diff hunks keyed by node id. Internally consistent: passes `validate_graph_view` |
| `analysis_running.json` | Running state as served (`{"analysis": {"public_id", "status"}}`) |
| `analysis_failed.json` | Failed state with `error_code` and `error_message` |
| `analysis_no_session.json` | Done, `banner.kind = no_session`, empty reasons and findings |
| `analysis_large.json` | Generated at the 200-node / 500-edge cap, to check speed and layout time |

`analysis_done.json` stays as is (it is used by server tests) and is also loaded by the UI tests to prove tolerance (§2.4, G63).

A pytest (`tests/test_contract_fixtures.py`) loads every fixture through `AnalysisResponse` and runs `validate_graph_view` on the `done` ones (except `analysis_done.json`, until it is fixed), so the fixtures cannot drift from the contract.

MSW handlers: `GET /api/analyses/:id` (fixture by `?fixture=` or by id), `401`/`403`/slow switches via `?mock=401|403|slow`.

---

## 14. Testing

| Test | Tool | Checks |
|---|---|---|
| `toFlow` unit tests | vitest | Every fixture: frames nest correctly, node types per G20, edges dropped per G63, chips placed per G26, expanded chips produce cards |
| Highlight unit tests | vitest | Selection, test path, nearest tested, blast radius depths and uncertain hops |
| Component smoke | vitest + Testing Library | Each card renders its fields for each tier |
| Layout | vitest (Node, ELK in-process) | Rich and large fixtures lay out without overlaps between siblings; large fixture under 2 s |
| Static render | Playwright (pre-installed Chromium) against `vite preview` with MSW | For each `done` fixture: `data-ready` within 5 s, no console errors, screenshot not blank; for running/failed: `data-error` set |
| CSP check | Playwright against the FastAPI server serving `web/dist` | No CSP violations in the console with the real header (closes status O3) |
| Contract fixtures | pytest | §13 |

`npm test` runs vitest; `npm run e2e` runs Playwright (with `--trace off`).

---

## 15. Server changes this plan needs

### 15.1 Let the render page read its analysis (blocker for the image)

`GET /api/analyses/{public_id}` should also accept a valid `render_token` for that `public_id` from an internal caller, in place of the viewer cookie. The checks already exist (`images.py` `_internal`, `verify_render_token`). Proposed shape: a dependency `viewer_or_render(public_id, request)` used only by `get_analysis`; the token arrives as `?render_token=` (the page copies it from its own URL). The token lives 60 s, which covers the fetch. Add a test: internal + valid token → 200; external + valid token → 401; internal + wrong id → 401.

Alternative considered: the `/render` route injects the analysis JSON into the HTML. Rejected: CSP blocks inline scripts, and it adds a second data path.

### 15.2 Remove the Dockerfile fallback

Once `npm run build` passes, change `npm run build || mkdir -p dist && touch dist/index.html` to `npm ci && npm run build` (G68).

### 15.3 Documentation fixes

`api-contract.md §5.2` (`diff_hunks` keyed by node id) and `ui-design.md §3.4` (`history` is a list) (G70).

No change to `api.py` is needed for the graph.

---

## 16. File layout

```
web/
├── package.json, package-lock.json
├── vite.config.ts                 # + worker format 'es', vitest config
├── playwright.config.ts
├── e2e/static.spec.ts
├── public/mockServiceWorker.js    # generated by msw init
└── src/
    ├── main.tsx                   # route by pathname: /a/:id, /render/:id
    ├── App.tsx
    ├── api/
    │   ├── generated/*.ts         # json-schema-to-typescript output (committed, G12)
    │   ├── client.ts              # fetch wrapper, 401 → login (G65), render_token (G58)
    │   └── useAnalysis.ts         # React Query, polling (G64)
    ├── mocks/
    │   ├── browser.ts, handlers.ts
    ├── graph/
    │   ├── PrGraph.tsx            # ReactFlowProvider + canvas + overlays
    │   ├── store.ts               # useGraphStore (G6)
    │   ├── toFlow.ts              # G62
    │   ├── highlight.ts           # §6.3
    │   ├── layout/
    │   │   ├── elk.worker.ts
    │   │   ├── useLayout.ts
    │   │   └── sizes.ts           # G22
    │   ├── nodes/  FileFrame, ClassFrame, ChangedCard, ContextCard, TestPill, GhostCard, CollapsedChip
    │   ├── edges/  CallEdge, ReachesEdge
    │   ├── useZoomTier.ts         # G60
    │   ├── useKeyboard.ts         # G47
    │   ├── Legend.tsx, ImpactSummary.tsx, SearchBox.tsx
    │   └── __tests__/
    ├── page/
    │   ├── GraphPage.tsx          # header, banner, canvas, inspector, states (§12)
    │   ├── Header.tsx
    │   ├── Inspector.tsx          # §5.3
    │   └── StaticPage.tsx         # §11
    ├── styles/ tokens.css, global.css
    └── assets/fonts/*.woff2
```

---

## 17. Build order and estimates

| # | Step | Est. | Depends on |
|---|---|---|---|
| 0 | Make `web/` build: fix `App.tsx`, lockfile, dev deps (G17), type generation (G12), vitest, MSW init | 0.5 h | — |
| 1 | Fixtures (§13) and the pytest that validates them | 0.75 h | — |
| 2 | `toFlow` + unit tests; ELK worker + `useLayout` | 1 h | 0, 1 |
| 3 | Node and edge components, tokens, legend | 1.25 h | 2 |
| 4 | Page shell: routing, `useAnalysis`, header, states (§12), inspector | 0.75 h | 3 |
| 5 | Selection, test path, nearest tested, chip expansion, keyboard, `?node=` | 0.75 h | 3 |
| 6 | Static mode + server change §15.1 + Playwright static test | 0.75 h | 4 |
| 7 | Blast radius and impact summary | 0.5 h | 5 |
| 8 | Semantic zoom, search, mini-map | 0.5 h | 5 |
| 9 | Dockerfile fallback removal, CSP check against FastAPI, doc fixes (G68, G70) | 0.25 h | 6 |
| | **Total** | **≈ 7 h** | |

Core for a working demo (dashboard click → graph → PR image): steps 0–6, about **5.75 h**.

---

## 18. Done when

- `npm ci && npm run build` passes with no fallback in the Dockerfile.
- `/a/{public_id}` opened from the dashboard shows the graph for every `done` fixture and for a real analysis from the server, with no console errors.
- `?node=` selects and centres the node.
- Running, failed and no-session states render as in §12.
- The server's render job produces the PR image from `/render/{id}?static=1` with the real page (not the stub), and `data-ready` is set within 5 s on the rich fixture.
- vitest, Playwright and the fixture pytest pass.

---

## 19. Open questions

| # | Question | Default if not answered |
|---|---|---|
| Q1 | Layout direction: top to bottom (G21) or left to right? | Top to bottom |
| Q2 | Dashboard URL for the "← Dashboard" link (G8), and does it have a per-session page the inspector can link to for evidence turns (§4)? | `/`; no evidence links |
| Q3 | Same tab or new tab from the dashboard (G4)? | Same tab (dashboard's choice; the graph works either way) |
| Q4 | Should the dashboard embed the graph as a component later (G6 keeps this possible)? | No; separate page |
| Q5 | Approve the server change in §15.1 (render token on `GET /api/analyses/{id}`)? Without it the PR image cannot be made by the real page | Build it in step 6 |
| Q6 | Fixtures: hand-written now (§13), or will real ones come from the server? | Hand-written; replaced by real ones when the session pipeline lands |

## 20. Decisions added after review

Status of this section: **Proposed** unless marked otherwise. Review layout: [PR graph layout wireframe](https://claude.ai/artifact/XpVTHjJDxsnDN1jn2qbWGW) (a Design canvas: the live page and the 1200 × 700 comment image).

### 20.1 One URL per analysis

| ID | Decision | Alternatives | Why |
|---|---|---|---|
| G71 | **Confirmed.** The canonical graph URL is `/a/{analysis_id}`, where `analysis_id` is the database primary key of the `analyses` row. The PR comment and the dashboard both link to this same URL for the same analysis | Keep `public_id` in the URL (current); a branch-based URL | The dashboard and the PR comment share one address per analysis, so a link can be pasted anywhere and shows the same page |
| G72 | Each branch has a database id (`tracked_branches.id`). `/b/{branch_id}` redirects (302) to the newest `done` analysis of that branch. Optional: only if the PR should always show the latest push | Only per-analysis URLs | A PR can be read as "latest state" without changing the per-analysis links |
| G73 | **Confirmed.** The PR comment always links to the latest push's analysis (`/a/{latest analysis id}`). Older analyses stay reachable from the dashboard | Link to the push each comment describes | Owner's call: the PR should show the current state |
| G74 | **Confirmed.** A missing analysis and an analysis the viewer cannot access both return `404`. The current `403 no_repo_access` is replaced for this route | Keep `403` | An unauthenticated or unrelated viewer should not learn which ids exist. Sequential ids make this more important |
| G75 | `public_id` stays as the random key for the image file name (`/img/{32 hex}`) and the render token. It is no longer in the page URL | Remove it | GitHub's image proxy caches by URL, so the image name must stay random |

**What changes in the code:** `Analysis.id` already exists as the primary key. The change is in `publish.py` (the link), `routers/live.py` and `routers/images.py` (route and lookup), and the contract (`AnalysisMetadata` gains `id`). Routes move to `/a/{id}`; the old `/a/{public_id}` should keep working as a redirect so links already posted in PR comments still open.

### 20.2 Why the render token exists

The PR image is made by a headless Chromium in the worker. It loads `/render/{public_id}?static=1&render_token=…` (`server/app/jobs/render.py`). The page then fetches `GET /api/analyses/{id}`, which normally needs a logged-in viewer cookie. The worker has no viewer, so without a token that request fails.

The token is a short-lived HMAC over `public_id` and an expiry time, created by the server just before it starts a render (`verify_render_token` in `routers/images.py`). It is valid for 60 seconds and is good for one analysis only. It lets the renderer read that one analysis without a user session, and it does not grant anything else.

Why not the alternatives:
- **A long-lived admin token** would let the renderer read every analysis. Rejected.
- **Injecting the JSON into the `/render` HTML** would avoid the second request, but the CSP blocks inline scripts, and it creates a second data path. Rejected.
- **Letting `/render` run without auth** would let any caller ask for renders. The route also checks that the caller is on loopback or a private network, so the token is a second check.

The token appears in the URL, so it can end up in logs. The 60-second lifetime limits that risk. Proposed follow-up (G76): the token could be sent in a header instead, if Chromium's request setup allows it for the page's own API calls.

### 20.3 Fixtures

Hand-written in `contract/fixtures/` (decision Q6 in §19: hand-written for now):

| File | Covers |
|---|---|
| `analysis_graph_rich.json` | The main development fixture. Two files, two classes, a `Retry` class. Changed cards of each kind (`added`, `functional`, `signature`, `text_only`), one ghost (`deleted`), one `outside_session` change, one `session_then_formatted` change, two tests with `REACHES` edges, one untested function with a `nearest_tested`, collapsed callers and tests, impact depths 1 to 3 with an uncertain hop, reasons for most nodes, two findings, diff hunks keyed by node id, and a timeline |
| `analysis_no_session.json` | Done, `no_session` banner, no reasons, no findings |
| `analysis_running.json` | Running state, as the API serves it |
| `analysis_failed.json` | Failed state with `error_code` and `error_message` |

Not written yet: `analysis_large.json` (generated, at the node and edge caps). It will come from a generator, not by hand.

`tests/test_contract_fixtures.py` validates the done fixtures through `AnalysisResponse` and checks their references (edges, reading order, impact hops, reasons, findings, hunks, timeline, paths and the stats totals). Result: 4 passed, 1 expected failure. The expected failure is `analysis_done.json`, which predates these rules (§2.4). It is kept as-is because the server tests use it.

### 20.4 Render token and the page

Before the UI is wired to the API, the render route needs the change in §15.1 (accept the render token on `GET /api/analyses/{id}`). Until then the image cannot be made from the real page.

### 20.5 Decisions after the owner's review

| ID | Decision | Status |
|---|---|---|
| G71 | `/a/{analyses.id}` is the canonical URL | Confirmed |
| G73 | PR comment always links to the latest push's analysis | Confirmed |
| G74 | Missing and forbidden analyses return 404 | Confirmed |
| G77 | The wireframe in the Design canvas is rejected. The owner asked for a graph style like Graphify and nexus-graph, and to use the Neo4j graph | Owner's direction; design to be re-proposed |

**Research (public pages, read through the web-fetch stand-in):**
- **GitNexus** names its renderer: Sigma.js (WebGL) with Graphology for the data, and LadybugDB (formerly KuzuDB) as the graph database. Licence PolyForm Noncommercial, so ideas only.
- **Graphify** (Apache-2.0 / MIT) exports a self-contained `graph.html`: a force-directed layout with colour by detected community, click, filter and search, edges tagged EXTRACTED or INFERRED, and an aggregated community view above 5,000 nodes. The renderer library is not named on the page. The earlier research in `ui-design.md` says vis-network; that is unverified.
- **nexus-graph** (AKhileshPothuri, MIT): a "neon graph UI" with a directory overview that drills into files and symbols. Stores the graph in SQLite. Renderer not named.

**Neo4j:** the repo does not show a deployed Neo4j. The server does not read it, and `docker-compose.yml` has no Neo4j service (status D1). The library has a Neo4j loader and a single-query region (`unpack_graph/neo4j_io.py`, `region.py`). Where the deployed instance runs, and what it holds, needs confirming before the design depends on it.

## 21. How the changes are rendered (design, after the second UI design document)

Status: **proposed.** Built on the design in `ui-design.md` (the second version reviewed by the owner), the current contract (`AnalysisResponse`) and `main` at `e4d0aa9`. Nothing here is built.

### 21.1 Where the data comes from

Every change is a node in `graph.nodes` with `change.kind` and `change.source`. Nothing is computed in the browser except layout, highlight and zoom. The inputs for drawing a change are:

| Drawing need | Contract field |
|---|---|
| Which functions changed, and how | `graph.nodes[].change` (`added`, `functional`, `signature`, `text_only`, `deleted`) and `change.source` |
| Who drove the change | `reasons[id].driver` |
| Whether a test reaches it | `graph.nodes[].test.label` and the `REACHES` edge |
| Reading order | `reading_order` |
| How far it reaches | `impact.by_node`, `impact.summary` |
| Findings | `findings`, `graph.nodes[].finding_ids` |

### 21.2 Rendering rules for each change

The same encoding is used in the PR view, the map and the static image, so a colour means the same thing everywhere.

| Change | Colour (stripe and badge) | Shape in the PR view | Shape on the map (dot) |
|---|---|---|---|
| Added | green | Full card, "ADDED" | Filled dot, green |
| Functional | amber | Full card, "MODIFIED" | Filled dot, amber |
| Signature | amber, bold outline | Full card, "SIGNATURE" | Filled dot, amber, ring |
| Text only | grey, muted | Compact card, "FORMATTING" | Small grey dot |
| Deleted | red dashed outline | Ghost card, struck name, "still called by N" | Hollow red ring at its old position |
| Outside session | amber badge "outside session" | As the change kind, with the badge | As the change kind, with a dashed ring |
| No test reaches it | red outline and flask | Adds "no test" to the footer | Red halo |

Context (not changed) is grey and compact. Tests are a pill, separate from the changed cards. Nothing uses emoji: icons come from `lucide-react` (G14), so they render the same in the PNG.

### 21.3 Large changes

The PR view stops being readable at about 40 changed functions. The server already caps the graph at 200 nodes and turns the rest into collapsed chips, but that does not help a refactor that changes 150 functions across 30 files.

**Rule (proposed, G78):** if more than 40 functions changed, the PR view opens in **file summary mode**:
- one card per changed file, with counts by change kind (for example "3 added · 7 modified · 1 deleted · 2 untested");
- the cards are laid out in reading order of their first changed function;
- clicking a file card expands it to its changed cards (the usual view for that file only).

The map (below) is the same data at a larger scale, so a big change is still visible as a whole.

### 21.4 The map (whole repository)

The docx puts the map in Sigma (WebGL) with deterministic folder packing (d3-hierarchy `pack`). This design keeps that and adds how the changes show on it:
- Every function is a dot. Changed dots use the colours in §21.2 and are drawn above everything else. Everything else is muted grey.
- Folders that contain a change get a tint. Folders with no change stay quiet.
- The blast radius (`impact.by_node`) is a heat glow on the affected dots. Uncertain hops are faint.
- Edges are hidden by default, as the docx says. Hovering or selecting a changed dot draws its callers and callees.
- Labels: folders always, files when zoomed in, functions on hover or close zoom.

The map's data is `GET /api/repos/{owner}/{repo}/map?sha=` (folder rows with `loc`, `fan_in`, `is_test`). That endpoint exists and is not yet used by any UI.

### 21.5 Static image (PR comment)

The image is the PR view in static mode at 1200 × 700, as the docx says. For a large change (§21.3), the image uses file summary mode. The image never shows the map. The renderer only needs HTML cards, so the text stays sharp.

### 21.6 Where Neo4j fits

The Neo4j question is answered by the repo, and it is not in production. The facts:
- `main` has no Neo4j service in `docker-compose.yml` (removed in `431450b`, D1 in `server-design.md`). The server does not import `unpack_graph/neo4j_io.py`.
- The graph branches (`graph/01` to `graph/12`, and `integrate/graph-stack`) still define a `neo4j:5-community` service with APOC, ports 7474 and 7687, and a volume.
- The library's Neo4j code (`neo4j_io.py`, the `--neo4j` flags, the single-query region in `region.py`) is on `main`.

So the Neo4j instance you have in mind may be (a) a stack built from the graph branches and run outside this repo, or (b) a deployment that was not committed. Neither can be confirmed from the repo. Before the design depends on Neo4j, we need the answer to "where does it run and what does it hold".

Options for rendering, depending on that answer:
- **N1 (proposed):** the server keeps computing the PR graph in-process, as now. Neo4j is not needed for the PR view or the image. The browser never talks to Neo4j.
- **N2:** Neo4j holds the map and the history (every analysis's changed functions), so a query can answer "what changed in this folder since last week". The server writes to it after each analysis. This needs the service back in compose and a write step in the worker.
- **N3:** the browser queries Neo4j directly. Rejected: it exposes the database and bypasses the access check on `/api/*`.

### 21.7 Decisions

| ID | Decision | Status |
|---|---|---|
| G78 | More than 40 changed functions opens in file summary mode (§21.3) | Proposed |
| G79 | The colours and shapes in §21.2 are the same in the PR view, the map and the image | Proposed |
| G80 | The map shows changed dots above the rest, folder tints for changed folders, and blast radius as a heat glow (§21.4) | Proposed |
| G81 | The PR view uses React Flow cards and the map uses Sigma with folder packing, as in the docx | Inherited (`ui-design.md` §2.2) |
| G82 | The browser never queries Neo4j (N3 rejected) | Proposed |
| G83 | Neo4j role: N1 for now (server computes the graph in-process). N2 only after the owner confirms where the instance runs and what it holds | Open (question to the owner) |
| G84 | The map's data comes from `GET /api/repos/{owner}/{repo}/map`, which exists but has no UI yet | Inherited (`ui-design.md` §6) |

### 21.8 Questions for the owner

1. Where does your Neo4j instance run, what does it hold, and is it reachable from the server? (It is not in this repo's compose file or in production.)
2. Is the card design (§3.2 of the docx: React Flow cards, colour stripes, reason lines) the right direction for the PR view, or should the PR view use dots with labels like GitNexus and Graphify?
3. Agree with the 40-function threshold for file summary mode (G78)?
