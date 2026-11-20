# Unpack documentation

Unpack turns AI-written code changes into an explained, explorable graph. For each pull request it shows what changed, why, and which parts no test reaches.

These documents describe the designs and the state of `main`. Start with the status document if you want to know what works today.

## Reading order

| # | Document | Read it for |
|---|---|---|
| 1 | [product-plan.md](product-plan.md) | What Unpack is, the buildathon scope, the six components, and what changed from the first plan |
| 2 | [status.md](status.md) | What is built, what was verified on `main`, what is missing, and the open decisions |
| 3 | [server-design.md](server-design.md) | The server: architecture, PR tracking, data model, API, jobs, the LLM calls, the GitHub comment, rendering, security, configuration |
| 4 | [session-pipeline.md](session-pipeline.md) | How a Gemini CLI session becomes per-function reasons, with evidence checked against the transcript |
| 5 | [cli-hook.md](cli-hook.md) | The CLI and the pre-push hook: what is found, trimmed, redacted and sent |
| 6 | [ui-design.md](ui-design.md) | The graph UI: the two views, the node shapes, the reasoning panel, the static image, the build plan |
| 7 | [graph-design.md](graph-design.md) | The code knowledge graph library: parsing, resolution, test reachability, change detection, validation, limits |

## Which document wins

If two documents disagree, use this order:

1. **[server-design.md](server-design.md)** is the source of truth for the API, the data model, the jobs and the rules around publishing. Its decisions are listed in §17.
2. **[session-pipeline.md](session-pipeline.md)** and **[ui-design.md](ui-design.md)** are the sources for the reasoning and the views. Where they conflict with the server design, the server design wins; their conflicts are listed in their §8 and §3.4.
3. **[graph-design.md](graph-design.md)** describes the library as built and measured. It is the reference for tiers, labels and limits.
4. **[product-plan.md](product-plan.md)** is the first plan, updated. Its changes are listed in §7.
5. **[status.md](status.md)** says what is true of `main` today. When a design and the code disagree, the status document records which one is authoritative for now.

## Components at a glance

```
Developer ── git push ──► CLI hook (cli-hook.md)
                               │  session, diff, redacted
                               ▼
                         Server (server-design.md)
                          ├─ code graph library (graph-design.md)
                          ├─ session pipeline (session-pipeline.md)   ← reasoning: placeholder today
                          ├─ PR comment on GitHub
                          └─ live graph page (ui-design.md)
```

## Conventions used

- **Status lines.** Each design document starts with a status line saying what is built. Items marked **Missing**, **Placeholder**, **Not verified** or **Open** are the ones to act on.
- **Open decisions** are numbered (`O1`, `O2`, …) in [status.md §4](status.md#4-open-decisions). Decisions already made are numbered (`D1`, `D2`, …) in [server-design.md §17](server-design.md#17-decisions-and-deviations).
- **Paths** are relative to the repository root. The code is in `server/`, `cli/`, `unpack_graph/`, `web/`, `contract/` and `schemas/`.
