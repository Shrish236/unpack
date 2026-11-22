# Unpack web

The UI: React 19, TypeScript and Vite. In production the server serves the built files at `/`.

```bash
npm install
npm run dev        # http://localhost:5173, proxies /api, /auth and /img to the server
npm run build      # type-check, then build to dist/
```

By default the dev server proxies to `http://localhost:8000`. Point it elsewhere with `UNPACK_API=https://... npm run dev`.

## Pages

Routing is by URL hash.

| Route | Page |
|---|---|
| `#/` | Product home |
| `#/exec` | Executive dashboard: adherence, repeat overrides, rework, agents |
| `#/team` | Manager view: teams and repositories, areas, funnel, suggestions |
| `#/pr` | List of PR analyses; `#/pr/<id>` opens one analysis |
| `#/govern` | Governance inbox: policy candidates, policies, rules, history |

The PR analysis page has the change graph (React Flow with ELK layout), the per-function reasons and evidence, the reading flow, the file diff, the session timeline and the decisions. A link of the form `/a/<id>` opens the same page.

## Source layout

```
src/
├── api.ts, queries.ts   # typed API client and React Query hooks
├── staticData.ts        # static snapshot mode (see below)
├── pages/               # one file per page, plus the home-page design studies
├── pr/                  # PR analysis sections
├── graph/               # change graph, inspector, layout
└── styles/              # tokens and per-page CSS
```

Types in `api.ts` follow the server's JSON, which is snake_case. The schemas are in [`../contract/schema/`](../contract/schema/) and `contract/fixtures/` holds sample responses.

## Static demo (GitHub Pages)

`VITE_STATIC=1` builds the app with no backend. Reads come from JSON files in `public/data/`, and decisions in the governance inbox show a read-only message instead of saving.

```bash
# refresh the snapshot from a running server (any server that answers the read endpoints)
node scripts/snapshot.mjs https://your-server.example.com

# build and preview it the way Pages serves it
VITE_STATIC=1 npm run build
npx vite preview
```

`scripts/snapshot.mjs` saves every endpoint the UI reads, one file per request. The file name comes from `snapshotName()` in `src/staticData.ts`; keep the two in step. The workflow in [`.github/workflows/pages.yml`](../.github/workflows/pages.yml) builds and publishes this on every push to `main` that touches `web/`. To enable it once, set Settings, Pages, Source to "GitHub Actions".

The snapshot contains quotes from real agent sessions, so only publish one made from data you are happy to make public.

Design: [docs/ui-design.md](../docs/ui-design.md) and [docs/ui-graph-plan.md](../docs/ui-graph-plan.md).
