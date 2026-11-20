# Governance pipeline: from a session to the dashboards

Every number on the executive, manager and governance pages is derived from one table of **decisions**, plus a few deterministic signals. Nothing on those pages is typed in by hand once the pipeline has run. The seeded rows (`make seed-dashboard`) are a labelled sample baseline; rows computed from real sessions carry `source = 'measured'`.

## Flow

```
agent session (Antigravity CLI or Gemini CLI)  ──►  parse into turns T1..Tn      pipeline/session.py, agy_session.py
repo at the pushed commit  ──►  steering files split into rules S1..Sn            pipeline/steering.py
turns  ──►  signals (no LLM)                                                      pipeline/signals.py
turns + rules + signals  ──►  decisions (LLM, then verified)                      pipeline/decisions.py
decisions + signals  ──►  dashboard rows (measured)                               pipeline/rollup.py
```

All of it runs inside `analyze_push` (`pipeline/analysis.py`) and is stored by `jobs/handlers.py`. The governance pass never fails an analysis: if it breaks, the graph and reasons are still stored and `signals.decision_error` says why.

## What needs no LLM

Read from the session JSON and the diff (`pipeline/signals.py`, `pipeline/session.py`):

| Signal | Source |
|---|---|
| Tool calls the human refused (`permission_denied` decisions) | tool status `cancelled` / `rejected` (Gemini), result status or text (agy) |
| Tool use and tokens per tool | tool names; message token counts split across the message's tool calls |
| Attempts | 1 + each failing test run that is followed by another edit |
| Flags `new-dependency`, `skipped-test` | added lines in manifests and test files |
| Flag `unsupported` | a `claim_not_backed` finding from the reasoning pass |
| Test facts | `pipeline/edit_linker.py` |

## What uses the LLM

One structured call per push (`llm/prompts/decisions_v1.md`, schema `LLMDecisionOutput`), purpose `decisions` in `llm_calls`:

- Human decisions: `redirect`, `reject`, `requirement`, `discussion`, each with a type, a verbatim quote and a **statement**: the correction rewritten as a short reusable rule. The statement is what lets the same correction in different sessions be recognised as one thing.
- Agent decisions: `choice`, with the steering rule that applied and whether it was followed.
- Highlights: what went right and what went wrong.

**Verification.** Every decision's quote must appear verbatim in its turn. A human decision must sit on a `user` turn, an agent decision on an agent turn, and a rule id must exist in the snapshot. Anything else is dropped and counted in `signals.decisions_rejected`. The same rule as the function reasons: no quote, no claim.

## Rollup (`pipeline/rollup.py`)

Runs after each analysis and on `make rollup`. Idempotent: it rebuilds `measured` rows from `decisions`; sample rows are never touched.

- **Team PR rows:** one per measured session (agent, decisions, overrules, attempts, flags). Shown under `DASHBOARD_TEAM_ID` (default `payments`) until a team mapping exists.
- **Policy candidates:** human overrides with a statement are grouped by type and word overlap (Jaccard ≥ 0.4). A group seen in at least `CANDIDATE_MIN_SESSIONS` (default 2) distinct sessions becomes a candidate whose evidence rows are the real decisions and quotes. Approved or rejected candidates are kept, not rebuilt.
- **Steering rule adherence:** counts of followed and violated per rule text, from the decisions that cite a rule.
- **Executive strip:** `GET /api/dashboard/exec` returns a `measured` block (sessions, decisions, human interventions, adherence, tool calls, tokens, flags).

## API

- `GET /api/analyses/{id}` has a `governance` block: decisions, highlights, flags, tool stats, attempts, steering files and rule count.
- Dashboard and governance responses mark each row `source: sample | measured`.

## Configuration

- `REASONING_ENABLED=true` and a `GEMINI_API_KEY` turn on the LLM calls. Without them, parsed decisions (refused tool calls) and all signals are still produced.
- `GEMINI_MODEL_PRIMARY`, `GEMINI_MODEL_FALLBACK`, `GEMINI_MODEL_REPAIR` must be models the key can call. List them with `client.models.list()`.
- Steering files read: `GEMINI.md`, `.gemini/GEMINI.md`, `AGENTS.md`, `CLAUDE.md`, and markdown under `.agents/rules`, `.agents/skills`, `.agent/rules`, `.agent/skills`, `.gemini/skills`.

## Capture rules (checked against real sessions)

- **Antigravity edits** use `edit_file(Path, Target, Replacement)` and `read_file(Path)` with absolute Windows paths. The parser maps them to repo-relative paths, writes a diff from Target and Replacement, and `reconstruct_edit_states` replays each edit over the base file so the edit linker has whole-file before and after states. An edit whose Target is not in the file is left unlinked.
- **Denied tool calls** (Antigravity): a `GENERIC` step with status `ERROR` and an `error` field containing "user denied permission". Other `ERROR` steps (for example a non-absolute path) are not denials.
- **Tokens**: Antigravity gives `input_tokens` and `output_tokens` per model step. Gemini CLI gives `tokens` per message; the CLI hook now keeps it (numbers only). A message's tokens are split across its tool calls.
- **Session identity**: `signals.session_key` (Gemini session id, or a hash of the first request and first timestamp). The same conversation pushed several times counts once in the rollup, using its latest analysis.
- **Graph failures**: if the graph cannot be built (clone failed, commit unavailable), the session is still parsed and its signals and decisions are stored. The analysis shows as failed, the governance numbers still count.

## What the LLM sees

| Call | Input |
|---|---|
| reasons (`reasons_v2.md`) | user turns, changed functions with edit turns, **CODE CONTEXT** (signature, callers, callees, test reach per changed function), facts (last test run, tests that reach each function), the session |
| decisions (`decisions_v2.md`) | user turns, steering rules, refused tool calls, **CHANGED CODE** (same graph context), signals (attempts, flags), the session |
| graph notes (optional, `LLM_GRAPH_TOOLS=true`) | the model calls `find_function`, `get_callers`, `get_callees`, `get_source`, `get_tests` on the head graph, then writes up to 12 notes that are added to the reasons prompt as **CODE NOTES** |

Graph content is context only. The verifier accepts quotes from the session alone, so a graph fact cannot become evidence.

## Not built

- Team mapping from paths or CODEOWNERS (all measured sessions land under one team).
- Real developer identity (the `dev` hash is derived from repo and branch).
- Time series on the executive charts from measured data (they stay on the sample baseline).
- Enforcement of `check` / `gate` policies as GitHub check runs.
