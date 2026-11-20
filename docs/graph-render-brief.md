# Graph rendering brief

Status: **brief, for design and build.** Covers only how the code graph is drawn: the canvas, nodes, edges, selection, blast radius, reasoning readouts, and the static PR image. Page chrome (dashboard, login, session screens) is out of scope.

## 1. What the graph must do

The graph is for a reviewer who has not written the code. In a few seconds they should see:

1. **What changed:** which functions were added, modified, removed, or changed outside the session.
2. **Why:** the reason for each change, who drove it (user asked, agent decided, not stated), and the evidence.
3. **Whether it is tested:** which changes no test reaches, and the shortest test path for the ones that are.
4. **What it touches:** callers and callees, and the blast radius at 1, 2 and 3 hops, with uncertain paths marked.
5. **Where it sits:** the change inside the whole repository, large repositories included.

The graph is an analysis tool, not a diagram. The reasoning matters as much as the shape, so text must be readable without hunting.

## 2. Data

Source: `GET /api/analyses/{id}` returns `AnalysisResponse` (`server/app/schemas/api.py`). Nothing is invented in the UI.

| Need | Field |
|---|---|
| Nodes | `graph.nodes[]`: `kind` (file, class, function, method, test), `layer` (container, changed, neighbor, test, ghost), `parent`, `path`, `start_line`, `signature`, `is_async`, `is_public`, `change`, `test`, `callers_count`, `callees_count`, `finding_ids` |
| Edges | `graph.edges[]`: `kind` (CALLS, REACHES), `tier` (EXTRACTED, INFERRED, AMBIGUOUS). Import, inheritance and override edges are not sent yet |
| Collapsed groups | `graph.collapsed[]`: "+12 callers in _api.py" |
| Reasons | `reasons[id]`: `reason`, `driver`, `history[]` (`turn`, `text`), `confidence`, `evidence[]` (`turn`, `quote`) |
| Findings | `findings[]`: `kind`, `finding`, `functions`, `evidence` |
| Blast radius | `impact.by_node[id]`: hops with `depth`, `tier`, `uncertain` |
| Reading order | `reading_order[]` |
| Diff | `diff_hunks[node_id]` |
| Status | `analysis.status`, `banner` (`no_session`, `reasons_unavailable`, `partial_coverage`) |

Size: the server caps the graph at 200 non-container nodes and 500 edges. Everything beyond that is in `collapsed`. The whole-repository map is a separate endpoint, `GET /api/repos/{owner}/{repo}/map?sha=`, and can reach about 12,000 functions in a real package (measured on SQLAlchemy: 11,756 functions, 59,221 call edges).

## 3. Visual references

Looked at for this brief:

- **Graphify** (`docs/graph-hero.png` in its repo, and graphify.com): dark canvas. Dots coloured by detected community, dense and faint edges, labels only when there is room, and a right-hand legend listing each community with a checkbox and a count. This is the density and atmosphere to aim for: a graph that reads as a system at a glance.
- **GitNexus** (gitnexus.vercel.app): its graph view needs a local server, so it could not be captured. Its README names Sigma.js (WebGL) and Graphology. Licence is PolyForm Noncommercial: use it for ideas only, copy no code and no assets.

What to learn from them: colour carries the grouping, the canvas is dark and quiet so the coloured dots carry the detail, edges stay faint until asked for, and a side legend does the filtering. What to avoid: a graph that is only dots with no way to read a change. Graphify puts the detail in a side panel, and that is where our reasoning goes.

## 4. Requirements

### 4.1 Canvas and nodes
- Dots, not cards, on the main canvas. Size encodes lines of code or fan-in; colour encodes the change. Unchanged context is grey and small.
- Changed nodes are the brightest things on the canvas. Everything else recedes.
- Labels: changed nodes always get a label at a readable zoom. Context nodes get labels on hover or close zoom only.
- Removed functions: hollow ring at their last known position, labelled "removed".
- Changed outside the session: dashed ring.
- No test reaches a changed node: a red halo.
- Test nodes: small, a separate colour, not competing with changes.
- Containers (files and classes): a faint region or hull, never a box with a heavy border.

### 4.2 Edges
- Solid for EXTRACTED, dashed for INFERRED, dotted and faint for AMBIGUOUS.
- Hidden by default. Showing the edges of a selected node draws its callers and callees. Showing all edges is an explicit toggle.
- A test path on selection is drawn in one colour, distinct from calls.

### 4.3 Selection and focus
- Clicking a node selects it and dims everything not connected to it (about 25% opacity).
- Blast radius: depth 1, 2, 3 in three decreasing strengths. Uncertain hops are drawn faint and labelled.
- Keyboard: arrows move through the reading order, Esc clears, `/` searches, `B` toggles blast radius, `F` fits the view.

### 4.4 Reasoning readouts (must be readable, not hunted for)
The selected node opens a panel with:
- The change kind and source, in words, not just colour.
- The reason in full, the driver, and the confidence.
- The history as a list of turns: "T14 wrapped send() in a loop → T15 test failed → T22 moved the retry here".
- Each evidence quote as a block with its turn number. Quotes are the proof, so they are shown in full.
- The findings that name this node.
- "No reason found in the session" when there is none. Do not leave the panel empty.
- The test path, or "No test reaches this" with the nearest tested function.

A small banner states what is missing for the analysis (no session, reasons unavailable, partial coverage). Missing data is shown, never silently skipped.

### 4.5 Scale
- Up to 200 changed and context nodes: full detail, labels, edges on selection, smooth pan and zoom.
- Up to about 12,000 functions (the map): WebGL dots, labels only for changed nodes and on zoom, edges hidden. Measure before promising a frame rate; numbers are in `docs/ui-graph-plan.md` §22 once the benchmark is recorded.
- Large changes (over 40 changed functions): a file summary first, with the graph opened per file.
- Whatever cannot be drawn is counted, never silently dropped: "+N more not shown".

### 4.6 Static image (PR comment)
- 1200 × 700 at 2×, rendered by the server's headless browser.
- Same visual language as the live page. No panels, no controls, a title strip with repository, PR and commit, and a legend.
- The page sets `data-ready="true"` only after layout and the first paint, `data-error` on failure. No console errors.

### 4.7 Technical constraints
- React 19, TypeScript, Vite. Dots and the map: Sigma v3 with Graphology (WebGL). Cards and reading panels: HTML.
- Layout for the change view: ELK in a Web Worker. Folder packing (d3-hierarchy `pack`) for the map.
- CSP: `default-src 'self'`, inline scripts blocked, `worker-src 'self' blob:`. Fonts bundled.
- Dark theme first; a light theme is required for the static image only if the PR comment background needs it. Decide and state it.
- Accessible: keyboard operable, visible focus, colour is never the only signal (shape and text carry the change kind too), contrast at least 4.5:1 for text.

## 5. Acceptance

The graph is accepted when:
- A reviewer can name what changed, what is untested, and why, within 10 seconds of opening it, on a real analysis.
- Selecting any changed node shows its reason, evidence and test path without leaving the canvas.
- The static image, rendered from the same code, is readable at 1200 × 700.
- The map stays interactive at the measured size, and a fallback exists beyond it.
- No console errors, and every fixture in `contract/fixtures/` renders.

## 6. Prompt for Claude Design

Paste the block below into Claude Design. It is self-contained.

```
Design and build the code graph view for "Unpack", a tool that explains the changes an AI coding agent made in a pull request.

WHAT IT SHOWS
A reviewer who did not write the code opens one analysis. They need to see, within 10 seconds: which functions changed (added, modified, removed, changed outside the agent's session), why each changed (the reason, who asked for it, the evidence quotes), which changes no test reaches, and what the change touches (callers, callees, blast radius at 1-3 hops, uncertain paths marked). The reasoning is the product, so readable text matters as much as the shape.

VISUAL REFERENCE
Graphify: a dark canvas with dense, coloured dots grouped by community, faint edges, and a right-hand legend with a checkbox and a count per group. Aim for that density and quiet atmosphere. Its weakness is that details sit only in side panels; we need the reasoning readable in place.
GitNexus: WebGL dots with labels, all detail in side panels. Use for ideas only.
Do not copy code, assets or layouts from either.

MAIN CANVAS
- Dots, not cards. Changed functions are the brightest, largest dots. Unchanged context is small and grey. Tests are a separate small colour.
- Change encoding (shape and colour; never colour alone): added = green dot; modified = amber dot; signature change = amber dot with a ring; formatting only = muted grey; removed = hollow red ring at its last position, labelled "removed"; changed outside the session = dashed ring; no test reaches it = red halo.
- Containers (file, class) are faint regions, not boxes.
- Edges: hidden by default. Solid for confirmed calls, dashed for inferred, dotted and faint for ambiguous. Selecting a node shows its callers and callees. Test paths drawn in a distinct colour.
- Click a node: it is selected and everything not connected dims to about a quarter opacity. Blast radius toggles on at hops 1, 2 and 3 with three decreasing strengths; uncertain hops are faint and labelled.
- Labels: changed nodes always labelled at readable zoom; context labelled on hover or close zoom.
- Keyboard: arrows step through the reading order, Esc clears, / searches, B toggles blast radius, F fits the view.

REASONING PANEL (opens on selection; must not be empty)
- Change kind and source written out in words.
- The full reason, its driver ("User asked" / "Agent decided" / "Not stated"), and confidence.
- History as a list of turns: "T14 wrapped send() in a loop -> T15 test failed -> T22 moved the retry here".
- Each evidence quote as a full block with its turn number.
- Findings that name this node.
- "No reason found in the session" when there is none.
- The test path, or "No test reaches this" with the nearest tested function.
- A banner states what is missing for the analysis (no session, reasons unavailable, partial coverage).

SCALE
- Up to 200 changed and context nodes: full detail and smooth pan and zoom.
- Up to about 12,000 functions for the whole-repository map: WebGL with Sigma v3 and Graphology, labels only for changed nodes and on zoom, edges hidden.
- Over 40 changed functions: show a per-file summary first; open a file to see its graph.
- Anything not drawn is counted ("+N more not shown"), never silently dropped.

STATIC IMAGE
1200 x 700 at 2x, rendered by a headless browser. Same visual language, no panels or controls, a title strip (repository, PR number, commit), and a legend. The page sets data-ready="true" after layout and first paint, data-error on failure, with no console errors.

TECHNICAL
React 19, TypeScript, Vite. Sigma v3 + Graphology for the dot canvas. HTML for panels and text. ELK (elkjs, in a Web Worker) for the change layout. d3-hierarchy pack for the map. The served page has CSP default-src 'self' with no inline scripts; bundle fonts; no CDN.

DELIVER
1. A design system: palette for dark (primary) and light (for the static image), type scale, change colours, and the shape vocabulary above, shown on one board.
2. The main canvas in its states: default, node selected, blast radius on, a removed function, a no-test node, a large change (summary), and no session.
3. The reasoning panel in the same states.
4. The 1200 x 700 static image.
5. Code for the canvas, panel and static page, with fixtures.

ACCEPTANCE
- A reviewer names the change, the untested code and the reason within 10 seconds.
- Selecting a changed node shows its reason, evidence and test path without leaving the canvas.
- The static image reads at 1200 x 700.
- No console errors. Every fixture in contract/fixtures/ renders.
```

## 7. Open points

- Dark or light for the static PR image.
- Whether the map ships in the first release or after the change view.
- The render numbers from the benchmark (pending), which set the node and edge caps the design can promise.
