# UI design: decisions and structure

Status: **design.** `web/` on `main` is a placeholder page. The packages in `web/package.json` are declared (React Flow, Sigma, ELK, d3-hierarchy, zustand, React Query, Shiki, MSW) but the views are not built. See [status.md](status.md).

What the UI must do, why the stack changed, and how the views are built. Based on reading the UIs of Graphify, codegraph, codebase-memory-mcp (CBM Lens), GitNexus (ideas only, non-commercial licence) and code-review-graph.

The server's contract is the source of truth for every field: [server design §5.5](server-design.md#55-live-graph). The UI never invents fields.

## 1. What the UI must do (in priority order)

1. **Show the PR's changes:** which functions were added, modified or deleted, clearly, at a glance.
2. **Show the reasoning comfortably:** why each function changed, who drove it, its history and its evidence, readable without hunting.
3. **Show what each node is:** kind (function, method, class, test, file), signature, file, callers, callees, imports, tests.
4. **Show the blast radius:** what calls into the change, how far, and how confident the paths are.
5. **Show the whole codebase:** where the change sits in a large repository, monoliths included.
6. **Produce the static image** for the PR comment, from the same code.

Items 1 to 4 need **readable, rich nodes with text**. Item 5 needs **thousands of nodes at speed**. No single renderer does both well. That is the main finding below.

## 2. Re-evaluating the stack

### 2.1 What the research showed

| Tool | Renderer | What happened |
|---|---|---|
| Graphify | vis-network (canvas), force layout | Good overview, colours by community; nodes are dots, and reading text needs the sidebar |
| GitNexus | **Sigma.js + Graphology** (WebGL) | Scales to large repositories; nodes are dots with labels; highlight and blast radius shown by colour; all detail lives in side panels |
| code-review-graph | D3 force (SVG) | Collapsible file clusters; slows down as graphs grow |
| CBM Lens | three.js (3D) | Impressive, but harder to read and costly to build |
| codegraph | **Svelte Flow** (HTML boxes) + fixed layered layouts | Dropped the force-directed hairball; boxes with text and structured layouts made the graph *readable*. Its biggest UI win |

The pattern: **WebGL dot graphs win on size; HTML box graphs win on understanding.** Unpack's core (items 1 to 4) is about understanding.

### 2.2 The decision: two views, two renderers, one data model

| | PR view (primary, opens by default) | Codebase map (context) |
|---|---|---|
| Purpose | Read the change: cards, reasons, callers, tests, blast radius | See where the change sits in the whole repository |
| Size | 20 to 500 nodes | 1,000 to 100,000 nodes |
| Renderer | **React Flow** (`@xyflow/react`): every node is a React component (a card); DOM text, crisp and interactive | **Sigma.js v3 + Graphology**: WebGL, fast at large sizes |
| Layout | **ELK** (`elkjs`, layered, compound groups for file and class) in a Web Worker | **Deterministic folder packing** (d3-hierarchy pack: folder → file → class → function), computed in the browser |
| Why | Rich shapes, text and badges are simple in HTML; the PNG for the PR comment gets sharp text | Scales; the packing layout never moves between commits and never becomes a hairball |

Both views read the **same data** and share **one selection state**: selecting a function in one view selects it in the other.

### 2.3 Why the earlier choice (Sigma for everything) changed

- Sigma draws nodes in WebGL. Shapes are possible (`@sigma/node-border`, `@sigma/node-square`, icons through `@sigma/node-image`), but **cards with text, badges and a reason line are not**. That would mean an HTML overlay per node, which loses Sigma's speed and is fiddly.
- React Flow is HTML: a node can be any component (card, chip, container). It handles hundreds of nodes well and can skip drawing off-screen nodes (`onlyRenderVisibleElements`), but it is **not** for tens of thousands of nodes.
- So each library does the job it is best at. Sigma stays, but only for the map.

### 2.4 Alternatives considered

| Option | Why not |
|---|---|
| Sigma only | No rich cards; reasoning stuck in side panels |
| React Flow only | Whole-repository function graph too large for the DOM on real monoliths |
| Cytoscape.js | Canvas; compound nodes are good, but HTML cards need extensions; awkward styling |
| vis-network | Canvas, dated styling, limited node content |
| D3 SVG | Everything hand-built; slows past a few thousand elements |
| three.js (3D) | Hard to read, slow to build; looks good only in a GIF |

### 2.5 Final frontend stack

| Concern | Choice | Licence |
|---|---|---|
| App | React 19 + TypeScript + Vite | MIT |
| PR view | `@xyflow/react` | MIT |
| PR view layout | `elkjs` (Web Worker) | EPL-2.0 (use as a library is fine) |
| Map | `sigma` v3 + `graphology` + `@sigma/node-border` | MIT |
| Map layout | `d3-hierarchy` (pack) | ISC |
| State | `zustand` (selection, filters, timeline position) | MIT |
| Data fetching | `@tanstack/react-query` | MIT |
| Code in panels | `shiki` (syntax highlight, read-only; lighter than Monaco; JavaScript regex engine, no WebAssembly) | MIT |
| Mock API during development | `msw` (Mock Service Worker) serving the contract fixtures | MIT |
| Types from the server contract | `json-schema-to-typescript` | MIT |
| Styling | CSS variables and CSS modules (light and dark), bundled fonts | — |
| Icons | `lucide-react` (declared in `package.json`) | ISC |

Built to static files and served by FastAPI ([server design §2](server-design.md#2-how-the-server-relates-to-the-frontend-no-separate-node-server)). No Node server.

## 3. The PR view (core)

### 3.1 Layout

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ Top bar: repo · PR #12 · commit picker (a1b2c3d ▾) · [PR view | Codebase map] · search│
├───────────────┬──────────────────────────────────────────────────┬───────────────────┤
│ Change list   │ GRAPH CANVAS (React Flow)                        │ Detail panel      │
│ (left, 280px) │                                                  │ (right, 420px)    │
│               │ ┌─ httpx/_client.py ─────────────────────┐       │                   │
│ Summary       │ │ ┌ class Client ──────────────────────┐ │       │ Tabs:             │
│ ⚠ 2 findings  │ │ │ [card] send  [card] _send_single…  │ │       │ Why | Code |      │
│               │ │ └────────────────────────────────────┘ │       │ Callers | Tests   │
│ Changes in    │ │ ┌ class AsyncClient ─────────────────┐ │       │                   │
│ reading order │ │ │ [card] _send_single… ⚠             │ │       │                   │
│ 1 Client.send │ │ └────────────────────────────────────┘ │       │                   │
│ 2 …           │ └────────────────────────────────────────┘       │                   │
│               │ [+12 callers in _api.py] [3 tests]               │                   │
│ Filters       │                                                  │                   │
├───────────────┴──────────────────────────────────────────────────┴───────────────────┤
│ Session timeline: T1 ── T14✎ ── T15✗ ── T22✎ ── T41✓ ── T45 💬   [▶ replay]          │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

- **Left: change list.** The summary, review findings, and every changed function **in reading order** (call order from the entry point down; computed by the server). Clicking an item focuses its card.
- **Centre: the graph.** Changed functions plus context, grouped by file and class.
- **Right: detail panel.** Everything about the selected node, with the **Why** tab open by default.
- **Bottom: session timeline.** The agent's turns as ticks: edits, failed and passing test runs, claims.

### 3.2 Node types and shapes

Nodes are **shaped by what they are** and **styled by what happened to them**.

| Node | Shape | Content |
|---|---|---|
| **Changed function or method** | Large card (about 260 × 110) | Kind icon and name · file:line · signature (one line) · **change badge** · **driver chip** · **one-line reason** · footer: ↑ callers ↓ callees · test status · ⚠ count |
| **Context function** (one hop out, unchanged) | Compact card (about 200 × 44) | Kind icon and name · file · ↑↓ counts |
| **Test** | Pill with a flask icon | Test name · pass or fail if known from the session |
| **Class** | Container frame around its methods | Class name · bases (for example "extends BaseClient") |
| **File or module** | Outer container frame | Path · **imports** listed in the header (collapsed to "imports 6 ▾") |
| **Deleted function** | Ghost card: dashed border, struck-through name | "Removed · still called by 2" |
| **Collapsed group** | Chip | "+12 callers in _api.py", "+3 tests"; click to expand |
| **Unresolved call** | Small dashed chip | "3 calls not resolved" |

**Card anatomy (changed function):**

```
┌───────────────────────────────────────────────┐
│ ƒ AsyncClient._send_single_request  MODIFIED  │  ← change badge
│ httpx/_client.py:1720 · async def (request)   │
│ ───────────────────────────────────────────── │
│ 👤 User asked                                  │  ← driver chip
│ "Mirrors the sync retry so both clients…"     │  ← one-line reason
│ ───────────────────────────────────────────── │
│ ↑ 2 callers  ↓ 3 calls  🧪 no test  ⚠ 1       │
└───────────────────────────────────────────────┘
```

**Visual encoding** (consistent across both views):

| Meaning | Encoding |
|---|---|
| Added | green left stripe and "ADDED" |
| Modified (logic) | amber left stripe and "MODIFIED" |
| Signature change | amber stripe and "SIGNATURE" |
| Formatting only | grey stripe and "FORMATTING"; card muted |
| Deleted | ghost card |
| Changed outside the session | badge "outside session"; reason shows "Not from the session" |
| Not reached by any test | red 🧪 and red outline |
| Review finding | ⚠ with count; colour by severity |
| Edge: confirmed call | solid arrow |
| Edge: inferred call | dashed arrow |
| Edge: ambiguous | dotted, faint |
| Edge: test reaches | thin green arrow (shown on selection) |
| Edge: imports | thin grey (shown on hover of a file header) |

### 3.3 Semantic zoom

React Flow exposes the zoom level, so the cards change with zoom:

| Zoom | Changed card shows | Context nodes |
|---|---|---|
| Far | Name and change colour only | Hidden behind group chips |
| Medium (default) | Full card minus the reason line | Compact cards |
| Close | Full card with the reason line | Compact cards with signature |

### 3.4 Where the reasoning lives (three levels)

1. **On the card:** driver chip and a one-line reason. Enough to scan the whole PR.
2. **Detail panel, Why tab** (default):
   - the full reason;
   - **history:** a small vertical timeline ("T14 tried wrapping `send()` → T15 test failed → T22 moved the retry into `_send_single_request`");
   - **evidence:** each quote as a block with its turn number, time and role (user, agent or test output). Clicking a quote opens the transcript drawer at that turn, with the quote highlighted;
   - **findings** for this function, each with its evidence;
   - "No reason found in the session", shown plainly when that is the case.
3. **Transcript drawer:** the session turns around the evidence (from `/api/analyses/{id}/turns`), so the reviewer can read the context.

Other panel tabs: **Code** (the function's diff, syntax highlighted), **Callers / Calls** (lists with confidence; click to jump), **Tests** (tests that reach it with the shortest path, or "no test reaches this" and the nearest tested neighbour), and **Imports** (the file's imports and who imports the file).

**Open conflict.** The UI wants `history` as a timeline of steps. The current contract (`FunctionReason.history`) is a single string. Decide the shape in the Pydantic models first ([status.md §4](status.md#4-open-decisions)).

### 3.5 Blast radius

- Toggle **"Blast radius"** in the top bar (or press **B** with a node selected).
- Shows callers **upstream** of the changed functions, by hop distance (1, 2, 3), coloured from strong to faint.
- Hop-1 callers appear as compact cards; hops 2 and 3 are grouped as chips per file ("+7 in _api.py"), expandable.
- Paths through inferred or ambiguous edges are drawn faint and labelled, so the impact is not overstated.
- A short summary in the left panel: "Reaches 23 functions in 6 files; 4 public API functions; 2 paths uncertain" (from `impact.summary`).

### 3.6 Tests on the graph

- Selecting a changed node with tests draws the **shortest test path** as green arrows (`test_retry` → `Client.get` → … → `_send_single_request`), adding the intermediate nodes as compact cards if they are not already shown. The server must put every node on a test path into `graph.nodes`.
- Selecting an untested node shows "No test reaches this" and highlights the **nearest tested neighbour**.

### 3.7 Session timeline and replay

- Ticks for each meaningful turn: ✎ edit (coloured by file), ✗ failed test run, ✓ passing run, 💬 user request, ⚑ claim.
- Hovering a tick shows the quote. Clicking selects the functions it touched.
- **Replay:** dragging or playing the scrubber lights up cards in the order the agent edited them. Edits later reverted flash and fade. This shows *how* the change was built; no other tool has the data for it.

### 3.8 Guided tour

"Walk me through it" steps through the change list in reading order: the canvas pans to each card, the panel shows its Why tab, and → moves on. It is built from the same reading order the server sends.

## 4. The codebase map (context)

### 4.1 Layout: folder packing, not force physics

- Every function is a dot inside its class, inside its file, inside its folder, using circle packing (d3-hierarchy `pack`), sized by lines of code.
- **Deterministic and stable:** positions depend only on the folder tree and sorted names, so the same function sits in the same place on every push, and the map never turns into a hairball. A new function appears inside its own file's circle.
- Works for monoliths: folders are visible as nested regions even at 100,000 functions.

### 4.2 What it shows

- Everything muted; **changed functions bright**, in the change colours; their files and folders tinted.
- **Blast radius** as a heat glow on affected functions.
- **Edges hidden by default** (that is what makes force graphs unreadable). On hover or selection, the node's calls and callers are drawn as curves.
- Labels for folders always; for files when zoomed in; for functions on hover or close zoom (Sigma's label threshold).
- Search (`/`) jumps to any function.

### 4.3 Links to the PR view

- Clicking a changed function opens it in the PR view, selected.
- Clicking any other function shows a small card (kind, file, callers, callees, tests), with "Show in PR view" if it is within the blast radius.
- A mini-map in the PR view's corner shows the packed map with the current change region outlined.

## 5. Static image for the PR comment

- The PR comment image is the **PR view** in static mode (`?static=1`): changed cards at medium zoom, findings visible, no panels, a title and a legend.
- HTML cards screenshot with sharp text (better than WebGL text).
- The page sets `data-ready="true"` only after ELK layout and the first paint are done, and `data-error` on failure ([server design §9](server-design.md#9-rendering-the-image-must-never-be-wrong)).
- Fixed size 1200 × 700 at 2× scale. If the change region is larger, fit to view with changed cards only, and add a "+N more in the live graph" chip.

## 6. Data the UI uses (server contract)

The server design ([§5.5](server-design.md#55-live-graph)) is the source of truth. What each part of the UI reads:

| UI part | Source |
|---|---|
| Cards, containers (file, class), edges | `GET /api/analyses/{id}` → `graph.nodes` (with `parent`, `signature`, `callers_count`, `callees_count`, `change`, `test`), `graph.edges` |
| "+12 callers in _api.py" chips | `graph.collapsed` |
| One-line reason, driver chip | `reasons[node_id]` |
| Change list order, guided tour | `reading_order` |
| Findings | `findings` |
| Blast radius | `impact.summary`, `impact.by_node` |
| Test path and nearest tested | `graph.nodes[].test`, and `REACHES` edges; full paths in node details |
| Session timeline and replay | `timeline` |
| Detail panel (Why, Code, Callers, Tests, Imports) | `GET /api/analyses/{id}/nodes/{node_id}`, `reasons`, and `GET …/turns?ids=` |
| Commit picker | `GET /api/prs/{owner}/{repo}/{n}/analyses` |
| Codebase map | `GET /api/repos/{owner}/{repo}/map?sha=` (rows: `id`, `kind`, `parent`, `loc`, `fan_in`, `is_test`), and `GET …/nodes/{id}/edges` on selection |
| Login state | `GET /api/me`; any 401 → redirect to `/auth/login?next=…` |

**Security note.** The Content-Security-Policy needs to allow inline styles (React Flow uses them) and, if ELK runs in a blob worker, `worker-src blob:`. Test this in the browser ([server design §11](server-design.md#11-security)). Shiki's JavaScript regex engine means no `wasm-unsafe-eval` is needed.

## 7. Build plan, in tiers

The earlier 8 to 10 hour estimate added up every feature. Splitting by value:

| Tier | Piece | Estimate |
|---|---|---|
| **Core** (the product; must ship) | Data layer: generated types, React Query, zustand, MSW mocks | 0.5 h |
| | PR view: React Flow canvas, ELK layout with file and class containers, changed and context cards, edges by tier, collapsed chips | 2 h |
| | Detail panel: Why tab (reason, history, evidence, transcript drawer), Code tab | 1 h |
| | Change list with findings; static mode for the PR image | 0.75 h |
| | Test path on selection; "no test reaches this" with the nearest tested neighbour | 0.5 h |
| | **Core total** | **≈ 4.75 h** |
| **Tier 2** (strong; build next) | Blast radius on the PR view | 0.75 h |
| | Session timeline (ticks, hover quotes, click to select) | 0.5 h |
| | Codebase map: Sigma with folder packing, change highlight, hover edges, link to PR view | 1.5 h |
| **Tier 3** (polish) | Replay on the timeline | 0.5 h |
| | Guided tour | 0.5 h |
| | Semantic zoom, mini-map, Callers, Tests and Imports tabs as rich views | 0.5 h |

Everything is about 9 hours, but only the core (about 5 hours) is required. It runs **in parallel** with the server, so it does not lengthen the critical path. Build order: core, then blast radius, timeline, map, and tier 3.

## 8. Building in parallel and joining at the end

### 8.1 Hour 1: contract (shared with the server)

- The server writes the Pydantic response models and runs `make contract`, producing `contract/schema/*.json` and `contract/fixtures/`:
  - `analysis_done.json`: the demo scenario (Client and AsyncClient retry, async untested, one claim finding, one deleted function, one outside-session change, collapsed callers, impact, timeline);
  - `analysis_running.json`, `analysis_failed.json`, `analysis_no_session.json`;
  - `node_*.json` for the key nodes; `turns.json`; `pr_analyses.json`;
  - `map_httpx.json` (the real httpx structure from the graph library).
- Until the graph produces real data, fixtures are written by hand to the schema.

**Status:** only `analysis_done.json` exists on `main`. The rest are missing.

### 8.2 UI build

- `web/` is a standalone Vite app. A `types` script (planned; not yet in `web/package.json`) generates TypeScript types from `contract/schema` with `json-schema-to-typescript`.
- **MSW** serves the fixtures at the real paths (`/api/analyses/:id`, …), with a switch to simulate 401, 403, slow responses and a running status.
- A **fixture picker** in development (`?fixture=analysis_failed`) to check every state.
- Tests: every fixture loads through the types; the static view renders each fixture without console errors and sets `data-ready`.

### 8.3 Joining (about one hour, near the end)

1. Server running locally with the demo analysis stored.
2. UI: disable MSW (`VITE_USE_MOCKS=false`); the dev proxy sends `/api`, `/auth` and `/img` to `http://localhost:8000`.
3. Walk the demo: open the link from the PR comment → log in → PR view → select the async function → Why tab → test path → map.
4. Fix any mismatch **in the Pydantic models first**, re-run `make contract`, and regenerate the types.
5. `npm run build`. The server Docker build copies `web/dist`. Check `/a/{id}` and the `/render` screenshot from the server.

### 8.4 Done when

- All four analysis states (done, running, failed, no session) render correctly from real server data.
- The PR comment image comes from the server's render and matches the live PR view.
- No console errors; `data-ready` is set within 5 seconds on the demo analysis.
