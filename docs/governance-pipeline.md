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

One structured call per push (`llm/prompts/decisions_v4.md`, schema `LLMDecisionOutput`), purpose `decisions` in `llm_calls`:

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

## Reading flow, file diff and decision links (per push)

- **File diff** (`pipeline/diff_files.py`, `analysis.diff_files`): every hunk, file by file, with the graph nodes that own it. Owner kinds: `function` (new-side lines overlap a changed function, or old-side lines overlap a deleted one), `class`, `module`, `file` (non-Python, or nothing in the graph), `none` (binary or too large to send). `diff_hunks` per function is derived from it, so the two cannot disagree.
- **Flow** (`analysis.flow`): `deterministic` is always there (callers before callees, grouped by call chain; `pipeline/flow.py`). `llm` is a second call (`llm/flow.py`) that names stages and gives each function a role and a note. It is verified: unknown or repeated labels are dropped, functions the model left out are appended, and the result always lists every changed function once. `warnings` records what was fixed. If the model fails or the quota is gone, `llm` is null and the deterministic flow is all the UI offers.
- **Decision links** (`pipeline/decision_links.py`): decisions carry `nodes` (from the model, checked against the graph, else from the edits that followed the decision) and an `outcome`: `rule_violated`, `overruled` (a person redirected, rejected or refused within 4 turns), `reverted`, `unverified` (a finding covers its functions) or `ok`. People's own decisions are `ok`.

## LLM limits and quota

`llm/client.py`: a quota error (429, `RESOURCE_EXHAUSTED`) stops at once with no retry, no fallback model and no repair call, and `llm/budget.py` makes every later call of the same push skip. Other errors retry with exponential backoff (`GEMINI_RETRY_BACKOFF_S`). Prompts over `GEMINI_MAX_INPUT_TOKENS` lose the middle. `GEMINI_CONCURRENCY` limits calls in flight. Tokens spent count against the daily budget even when the analysis then fails. A degraded analysis is still complete: every changed function has a reason row (`Not analysed ...` when the model did not run), the flow is the deterministic one, and the banner says why. A re-push of a head that first arrived without a session is analysed again with the session.

## Dashboard numbers (`pipeline/metrics.py`)

The dashboard routes compute measured numbers from `decisions`, `session_signals`, `function_reasons` and `analyses.facts` when at least `METRICS_MIN_SESSIONS` sessions exist, and replace the sample section by section. Each response has `sources: {section: sample | measured}`, and the pages show "Sample data" only on sections that have no measured source. Definitions: adherence = rule-followed decisions over decisions checked against a rule; repeat override = human corrections whose statement recurs in at least `CANDIDATE_MIN_SESSIONS` sessions, per 100 sessions; verified = sessions whose last test run came after the final edit with no unsupported claim; unrequested = functions with driver `agent_decided` over explained functions; rework = a session with an override, an added requirement or more than one attempt (cause `thin` when a person added a requirement, else `missed`). Weeks with nothing to measure are `null`, not zero.

`make fake-sessions` adds 15 made-up sessions (`unpack-dev/fake-sessions`) so every section and the PR page have data; `make fake-sessions-clear` removes them.

## API

- `GET /api/analyses/{id}` has a `governance` block: decisions, highlights, flags, tool stats, attempts, steering files and rule count.
- Dashboard and governance responses mark each row `source: sample | measured`.

## Prompt structure

Every system prompt has the same parts: **Your job**, **The input** (each `## SECTION` of the user message explained), the rules, **Output format** (a field table, a worked example, and the JSON Schema generated from the pydantic model that parses the answer, so the two cannot drift), and **Before you answer** (a checklist). Every user prompt ends with a `## RESPONSE` block naming the exact labels, rule ids, node ids and turn range the model may use. The text lives in `llm/prompts/`, is loaded by `llm/prompt_text.py`, and `tests/server/test_prompts.py` checks that the examples validate, every allowed value and field is described, and the schema in the prompt is the model's schema. Bump the version number in `prompt_text.py` (and add a new file) when you change a prompt; old files stay.

## Running without Gemini

`GEMINI_BACKEND=mock` with `REASONING_ENABLED=true` swaps the model for `llm/mock.py`. It reads the real prompts, writes answers that match the schemas and pass the same verification, and reports the model name `mock-gemini`. Use it to run the whole stack with no key and no quota. `tests/server/test_e2e_mock_llm.py` drives a real git repo and a real Gemini session through the CLI payload builder, ingest, the worker, the API and the dashboards. Set `UNPACK_DUMP_PROMPTS=<dir>` to write the exact prompts the model receives. To use a real key, set `GEMINI_BACKEND=ai_studio` and `GEMINI_API_KEY`; nothing else changes.

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
| reasons (`reasons_v3.md`) | user turns, changed functions with edit turns, **CODE CONTEXT** (signature, callers, callees, test reach per changed function), facts (last test run, tests that reach each function), the session |
| decisions (`decisions_v4.md`) | user turns, steering rules, refused tool calls, **CHANGED CODE** (same graph context), signals (attempts, flags), the session |
| flow (`flow_v2.md`) | user task, the changed functions with the verified reason for each, the calls between them, a default order. No session text |
| graph notes (optional, `LLM_GRAPH_TOOLS=true`) | the model calls `find_function`, `get_callers`, `get_callees`, `get_source`, `get_tests` on the head graph, then writes up to 12 notes that are added to the reasons prompt as **CODE NOTES** |

Graph content is context only. The verifier accepts quotes from the session alone, so a graph fact cannot become evidence.

## Not built

- Team mapping from paths or CODEOWNERS (all measured sessions land under one team).
- Real developer identity (the `dev` hash is derived from repo and branch).
- Suggestions and the cross-team consistency matrix on the team pages (they need a model pass over the criteria; they stay sample).
- Acceptance criteria. "Rework" is counted per session, not per criterion.
- Enforcement of `check` / `gate` policies as GitHub check runs.
