# Session pipeline: from a Gemini CLI session to per-function reasons

Status: **design.** The CLI side (finding, trimming, redacting, sending) is built; the server side (parsing turns, linking edits to functions, the LLM call, verification) is not. See [status.md](status.md).

Scope for the buildathon: **one Gemini CLI session per push, one repository, Python code, GitHub.** Items marked *(later)* are skipped unless time allows.

Where this document and the [server design](server-design.md) disagree, the server design wins (see [§8](#8-conflicts-resolved-against-the-server-design)).

## 1. The idea in one picture

```
Developer + Gemini CLI ──► git push
                              │
                 pre-push hook (local)          ← cli-hook.md
                 1. find the session file
                 2. trim it
                 3. remove secrets
                 4. send it with the diff
                              │
                              ▼
Server                        
 1. store the push, queue a job
 2. parse the session into turns [T1] [T2] …
 3. find the changed functions (diff + code graph)      ← code: facts
 4. map every session edit to the functions it touched  ← code: facts
 5. link each changed function to the edits that produced it ← code: facts
 6. one Gemini call: reasons, history, session review   ← LLM: understanding
 7. check every quote word for word                      ← code: honesty
 8. store the result permanently → PR comment + live graph
```

**The rule:** code establishes the facts (what changed, which edit did it); the LLM explains the *why*; code checks the LLM's evidence.

## 2. Gemini CLI session format (what is read)

Taken from the Gemini CLI source (`google-gemini/gemini-cli`, `packages/core/src/services/chatRecordingService.ts` and `chatRecordingTypes.ts`, commit `808199f`, 19 Nov 2026). **Check it against a real session from the installed version before relying on it** (see [§6](#6-build-order-and-checks)).

### 2.1 Where it lives

```
~/.gemini/
├── projects.json                     # { "projects": { "<abs project path>": "<shortId>" } }
└── tmp/<shortId>/chats/
    ├── session-2026-11-19T14-05-1a2b3c4d.jsonl   # main session
    └── <parentSessionId>/<subagentId>.jsonl      # subagent sessions (later)
```

- Older installs used `sha256(projectRoot)` as the folder name. Fall back to it when `projects.json` has no entry.
- Under the macOS sandbox the folder moves *(later)*.

### 2.2 File format

JSONL, append-only. Each line is one of:

| Record | Shape | Meaning |
|---|---|---|
| Header | `{sessionId, projectHash, startTime, lastUpdated?, kind?, directories?}` | First line |
| Message | `{id, timestamp, type, content, …}` | A turn. A later line with the **same `id` replaces** the earlier one |
| Patch | `{"$patch": {id?, content?, toolCalls?, updates?, removeIds?, orderIds?}}` | Updates, removes or reorders messages |
| Rewind | `{"$rewindTo": "<messageId>"}` | `/rewind`: that message and all after it are removed |
| Set | `{"$set": {summary?, …}}` | Updates header fields |

`type` is `user`, `gemini`, `info`, `error` or `warning`. `content` is a Gemini `PartListUnion` (a string, or a list of parts such as `{text}`).

A `gemini` message can also carry:

- `model?: string`
- `thoughts?: [{subject, description, timestamp}]`: thought summaries, not raw reasoning
- `tokens?: {...}`
- `toolCalls?: [{id, name, args, status, timestamp, result?, resultDisplay?, agentId?, description?, displayName?}]`

### 2.3 Tools that matter

| Tool | `args` | Why it matters |
|---|---|---|
| `replace` | `file_path`, **`instruction`**, `old_string`, `new_string`, `allow_multiple` | An edit. `instruction` is required, and the model is told to state WHY, WHERE and WHAT |
| `write_file` | `file_path`, `content` | Creates or overwrites a file |
| `run_shell_command` | `command`, `is_background` | Test runs, formatters, `sed`, `git` |
| `read_file`, `grep`, `glob` | `paths`, `patterns` | What the agent looked at |
| `write_todos` | `todos` | The agent's plan |

For `replace` and `write_file`, `resultDisplay` is a **FileDiff**:

```json
{ "fileDiff": "...", "fileName": "...", "filePath": "...",
  "originalContent": "whole file before, or null", "newContent": "whole file after",
  "diffStat": {}, "isNewFile": false }
```

This is the key property: **every edit records the exact file before and after**, including any auto-correction the CLI applied. The server never has to guess where an edit landed.

## 3. The pre-push hook

The hook is built; see [cli-hook.md](cli-hook.md) for commands, modules and the payload. In brief: it never blocks a push, trims the session (drops tokens and display-only fields, caps tool results at 20 KB, keeps FileDiff contents in full), scrubs secrets from every string, and sends one gzipped payload with a 5-second timeout.

The payload's session section:

```json
"session": {
  "agent": "gemini-cli",
  "agent_version": "<from `gemini --version` if cheap, else null>",
  "file_name": "session-2026-11-19T14-05-1a2b3c4d.jsonl",
  "lines": [ {…}, {…} ]
}
```

The server treats `lines` as parsed JSONL records, in order.

**Why send `base_content` and `head_content`:** the hook runs before the push reaches GitHub, so the server cannot fetch `head_sha` yet. Sending the changed files makes the job independent of timing. The server still fetches the repository later for the full graph.

## 4. Server pipeline

FastAPI and Postgres. A `jobs` table with `SELECT … FOR UPDATE SKIP LOCKED` is the queue; the worker runs the steps below. Details of queueing and retries are in [server design §6](server-design.md#6-jobs-and-the-worker).

### 4.1 Ingest

- Verify the repository token, decompress, validate against the payload schema.
- Store the raw payload (`pushes`, keyed by `head_sha`), enqueue an `analyze_push` job, return 202 with the push ID.
- Idempotent: the same `head_sha` twice reuses the stored analysis.

### 4.2 Parse the session into turns

Replay the JSONL the way the Gemini CLI does:

1. Header: metadata.
2. Message: put into an ordered map by `id`. A later line with the same `id` replaces it in place.
3. `$patch`: apply `content` and `toolCalls[].result` updates, `removeIds`, `orderIds`.
4. `$rewindTo`: drop that message and all later ones (same as the CLI). *(later: keep them flagged as rewound, because a user can rewind the conversation but keep the file changes.)*
5. `$set`: update metadata.

Then flatten into **turns** with stable IDs `T1`, `T2`, … in order:

| Turn kind | From |
|---|---|
| `user` | `type: user` message text |
| `assistant` | `type: gemini` message text |
| `thought` | each entry in `thoughts` (subject: description) |
| `edit` | `replace` or `write_file` call: path, instruction, status, FileDiff |
| `shell` | `run_shell_command`: command, exit status, output |
| `read` | `read_file`, `grep`, `glob`: what was looked at (output not passed to the LLM) |
| `plan` | `write_todos`: the list |
| `notice` | `info`, `error`, `warning` messages |

Paths are made relative to the repository root. This list is the **UnpackSession**, the agent-neutral format. Adapters for other agents produce the same type.

### 4.3 Find the changed functions (facts)

Using the code graph library on `base_content` and `head_content` of each changed `.py` file:

- functions matched by ID `path::Qual.Name`;
- each labelled `added`, `deleted`, `text_only` (same logic hash), `signature`, or `functional`;
- changed line ranges from the diff, attached for display.

Only these functions get reasons. `text_only` functions get a short automatic label ("comments or formatting only") and no LLM reasoning.

### 4.4 Map each session edit to functions (facts)

For every successful edit turn, parse `originalContent` and `newContent` with the same parser, compare function hashes, and record which functions the edit touched and each function's logic hash after the edit:

```
edit T14 → httpx/_client.py::Client._send_single_request   (logic hash a91f…)
edit T22 → httpx/_client.py::Client._send_single_request   (logic hash 03bc…)
edit T22 → httpx/_client.py::AsyncClient._send_single_request (…)
```

**Out-of-band changes.** For each file, the next edit's `originalContent` should equal the previous edit's `newContent`. If it does not, something else changed the file in between (a shell command such as `ruff format` or `sed`, or the user's editor). Record a synthetic change and credit it to the shell turns in between, or to `outside_session` if there were none. These appear in the timeline as `out_of_band`.

`extract_file(path, data)` takes bytes, so the server can parse `originalContent` and `newContent` in memory, without a checkout.

### 4.5 Link each changed function to its edits (facts)

For each changed function from §4.3:

1. Collect every edit that touched it, in order: its **edit history**.
2. Find the **last edit whose logic hash equals the committed version's logic hash**: the *final edit*.
3. Label where the change came from:

| Label | Rule |
|---|---|
| `session` | a session edit produced the committed logic |
| `session_then_formatted` | as above, but the committed text differs only in formatting |
| `session_partial` | edits touched it, but none matches the committed logic (it was changed again outside the session) |
| `outside_session` | no session edit touched it |

4. Edits to functions that are **not** in the final diff were reverted. Keep them as context, with no reason.

### 4.6 Build the LLM input

One call per push for the buildathon (a demo-sized session fits easily). If the trimmed input exceeds about 200k tokens, split by groups of functions that share edits; the server design's `reasons_part` call handles this ([server design §7.1](server-design.md#71-calls-per-analysis)).

**Trim for the LLM** (the stored session is untouched):

- replace each edit's full file copies with the **diff of just the functions it touched** (from §4.4);
- read turns: keep the path or pattern, drop the output;
- shell output: first 40 and last 60 lines, plus every line matching `FAILED|Error|Traceback|assert|passed|failed`;
- drop notice turns except errors;
- keep all `user`, `assistant`, `thought` and `plan` text in full.

**Input layout:**

```
## TASK
[T1] <user message, verbatim>
[T37] <later user message, verbatim>

## CHANGED FUNCTIONS
F1 httpx/_client.py::Client._send_single_request (functional, source: session)
   edits: T14, T22 (final)
F2 httpx/_client.py::AsyncClient._send_single_request (functional, source: session)
   edits: T22 (final)
F3 httpx/_config.py::Retry.__init__ (added, source: outside_session)

## FACTS (computed, do not contradict)
- Last test run: T41 `pytest tests/test_client.py` → exit 0, "18 passed"
- No test run after final edit T22? → false
- Tests that reach F2: none (from code graph)

## SESSION
[T1] user: …
[T2] thought: Planning retries — …
[T14] edit httpx/_client.py instruction: "To retry on connection errors, in _send_single_request, wrap …"
      diff: …
[T15] shell: pytest tests/test_client.py → exit 1
      output: … FAILED tests/test_client.py::test_retry …
…
```

### 4.7 The prompt and output schema

System instructions (summary):

- You are explaining **why** an AI agent made each code change, using **only** the session provided.
- For each function F#: give a one-to-two sentence reason, who drove it, and its history if there were several attempts.
- Every claim needs at least one **exact quote**, copied character for character from a turn, with its turn ID.
- If the session gives no reason, say `not_stated`. Do not guess. For `outside_session` functions, return `not_stated` unless a turn clearly explains them.
- Do not contradict the FACTS section.
- Then list **session review** findings that can only be seen in the session. No general code review of the diff.

The output is structured JSON (Gemini JSON mode). The schema uses lists of objects with fixed fields, not maps with dynamic keys, because the structured-output subset does not support them ([server design §7.4](server-design.md#74-request)).

```json
{
  "summary": "2–3 sentences: what the session set out to do and what was done",
  "functions": [
    {
      "fn": "F1",
      "reason": "…",
      "driver": "user_asked | agent_decided | not_stated",
      "history": [{"turn": "T14", "text": "tried wrapping send()"},
                  {"turn": "T15", "text": "test_retry failed"},
                  {"turn": "T22", "text": "moved the retry into _send_single_request"}],
      "evidence": [{"turn": "T1", "quote": "…"}, {"turn": "T22", "quote": "…"}],
      "confidence": "high | medium | low"
    }
  ],
  "session_review": [
    {
      "kind": "claim_not_backed | test_failed_ignored | not_tested_after_change | request_not_done | check_weakened | dead_end",
      "finding": "…",
      "functions": ["F2"],
      "evidence": [{"turn": "T45", "quote": "I've added tests covering both clients"}]
    }
  ]
}
```

**Open conflict:** the UI wants `history` as a vertical timeline of steps, but the current API contract (`FunctionReason.history`) is a single string. The model output above uses a list, which is a contract change. Make it in the Pydantic models first ([ui-design.md §3.4](ui-design.md#34-where-the-reasoning-lives-three-levels)). See [status.md §4](status.md#4-open-decisions).

**Session review kinds:**

| Kind | Example |
|---|---|
| `claim_not_backed` | The agent says "added tests for both clients"; the graph shows no test reaches `AsyncClient._send_single_request` |
| `test_failed_ignored` | A test failed and the agent moved on without fixing or mentioning it |
| `not_tested_after_change` | No test run after the final edit |
| `request_not_done` | The user asked for something that is not in the diff |
| `check_weakened` | A test was skipped, an assertion loosened, or a broad `except` added to make something pass |
| `dead_end` | An approach was tried and reverted (useful for the next reader) |

**Model:** a current Gemini Pro-class model (quality matters more than speed here). Use the model's default temperature, not 0 ([server design §7.4](server-design.md#74-request)).

### 4.8 Verify (code)

For every evidence item:

1. The turn ID exists.
2. The quote appears **verbatim** in that turn's text, after normalising whitespace and quote characters. For edits, match against the instruction or the diff.
3. A `user_asked` driver needs at least one quote from a user turn.

Then:

- A function reason with **no valid quote** becomes `driver: not_stated` with the reason "No reason found in the session". The original is kept in a hidden `rejected` field for debugging.
- A review finding with no valid quote is dropped.
- `claim_not_backed` and `not_tested_after_change` findings are **checked against the FACTS**; if the facts disagree, the finding is dropped.
- Unknown function IDs are dropped. Missing functions are added as `not_stated`.

Log the rejection counts. They are the quickest measure of quality while the prompt is tuned.

### 4.9 Store and hand off

| Table | Holds |
|---|---|
| `pushes` | raw payload, `head_sha`, branch, received time |
| `sessions` | parsed UnpackSession (turns) |
| `analyses` | the verified output, changed functions and edit links; **never regenerated** |
| `function_reasons` | one row per changed function (for the side panel) |
| `review_findings` | one row per finding |

Consumers:

- **PR comment:** summary, counts ("5 functions changed, 1 changed outside the session"), the review findings as flags (no transcript quotes; those stay behind the authenticated link), the graph image and the live link.
- **Live graph:** each changed node shows its reason, driver, history, evidence quotes with turn number and time, and its review findings.

**Where the rejected quotes go.** The design keeps them in a hidden field for debugging. No column exists yet; store them in `analyses.llm_raw` or add a column when the reasoning step is built.

## 5. What reviewers get

| For each changed function | Source |
|---|---|
| **Why** it changed | the user request, the edit's instruction, agent text, thoughts |
| **Who drove it** | user asked / agent decided / not stated |
| **How it got there** | earlier edits and the errors between them |
| **What triggered it** | the failing test or error just before the edit |
| **Whether it was verified** | test runs after the final edit |
| **Where it came from** | session / session then formatted / outside the session |

| For the whole push | Source |
|---|---|
| Summary of the session | LLM |
| Claims that don't hold | agent text against graph and test facts |
| Ignored failures, missing tests, unfinished requests, weakened checks, dead ends | LLM, each with a quoted turn |

Every reason and finding links to the exact turns it came from. If there is no evidence, it says so.

## 6. Build order and checks

1. **Session parser** (§4.2) on three real Gemini CLI sessions from the installed version. Confirm that `resultDisplay` carries `originalContent` and `newContent`, and that `replace` calls carry `instruction`.
2. **Hook** (§3). Find, trim, scrub; review `unpack push --dry-run` output by eye for secrets. *(Built; re-check against real sessions.)*
3. **Edit-to-function mapping and linking** (§4.4, §4.5) using the graph library. Check by hand on one session.
4. **LLM call and verification** (§4.6 to §4.8). Hand-label reasons for about 20 functions across the sessions. Track correct, partly correct and wrong, and the rejection counts after each prompt change.
5. **Demo session.** Record it deliberately in Gemini CLI on the httpx fork: a feature on both `Client` and `AsyncClient`, tests only for the sync path, one failed test run then a fix, one `ruff format`, and a final message claiming full tests.

## 7. Skipped for now *(later)*

- Several sessions per push; subagent sessions; keeping rewound edits.
- Commit trailer linking a commit to its session.
- Sending function-level edits instead of full file copies (less data and less secret exposure).
- Claude Code and other adapters (the same UnpackSession output).
- Splitting the LLM call by function group for very long sessions (the server design already covers this as `reasons_part`).

## 8. Conflicts resolved against the server design

| # | Where in this doc | Conflict | Resolution |
|---|---|---|---|
| 1 | §3 (earlier draft) | Posted to `{server}/ingest` with `repo.remote` | `POST /v1/ingest` with `repo.remote_url`, `owner`, `name`, `default_branch` |
| 2 | §4.6 | Split the LLM call above about 200k tokens; §7 said splitting is skipped | Kept as `reasons_part` in the server design; build it if the demo session needs it |
| 3 | §4.7 | `temperature 0` | The model default; Gemini 3 advises against changing temperature |
| 4 | §4.7 | `history` as one string in the server, a timeline in the UI | Open; proposed list of steps (see §4.7) |
| 5 | UI §3.2 | Node kind `module` | The server uses `file`; the UI uses `file` |
| 6 | §4.2 | Turn kinds | Matches the server: `user`, `assistant`, `thought`, `edit`, `shell`, `read`, `plan`, `notice` |
