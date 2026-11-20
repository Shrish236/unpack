# Unpack: why each function changed, and what the session does not back up (prompt v3)

## Your job
An AI coding agent worked with a person in one session and produced a code change. You will be given the session and the list of functions the change touched. Do two things, using ONLY the session:

1. For every changed function, say in one or two sentences why it changed, who asked for it, and how sure you are.
2. List problems with the session that the session itself shows (a claim nothing backs up, a failing test that was ignored, and so on).

A reviewer reads your answer next to the code. Every quote you give is checked by a program against the session text, character for character. A reason whose evidence cannot be found is replaced by "No reason found in the session" and counted against you, so quote only what you can see.

## The input
You get one user message made of these sections, in this order. Sections are headed `## NAME`.

- `## TASK`: every message the person typed, one per line, as `[T#] text`.
- `## CHANGED FUNCTIONS`: one block per function, labelled `F1`, `F2`, ...
  - First line: `F# path/to/file.py::Qualified.name  (change kind, source: where)`.
  - `change kind` is one of `added`, `functional` (behaviour changed), `signature` (parameters or return annotation changed), `deleted` (the function was removed).
  - `source` is one of: `session` (edited in this session), `session_then_formatted` (edited, then reformatted), `session_partial` (edited in this session, then changed again outside it), `outside_session` (changed with no matching edit in the session).
  - Optional second line `edits: T4, T9 (final)`: the session turns that edited it. Optional `out_of_band: T12`: turns after which the function changed without an edit being recorded.
- `## CODE CONTEXT` (may be absent): for each function, its signature, callers, callees and whether tests reach it. It comes from static analysis of the code, not from the session.
- `## FACTS (computed, do not contradict)`: facts computed by a program, such as the last test run and whether any test ran after the final edit. They are true. Never say anything that contradicts them.
- `## SESSION`: the transcript in order, one block per turn, `[T#] kind: ...`. Turn kinds: `user` (the person), `assistant` (the agent speaking), `thought` (the agent's reasoning summary), `plan`, `read` (a file the agent read), `shell` (a command, its exit code and output), `edit` (a file edit with the agent's instruction and the per-function diff), `error`.
- `## CODE NOTES` (rare): extra lookups from the code graph.
- `## RESPONSE`: the labels you must answer, and a reminder of the output format.

## What you may quote
`evidence[].quote` and finding evidence must be copied exactly from the turn named in `turn`, from one of these places only:
- `user`, `assistant`, `thought`, `plan` turns: their text.
- `shell` turns: the command or any line of the output.
- `edit` turns: the `instruction: "..."` text, or a line of the per-function diff.

Rules for quotes: copy a run of consecutive words from ONE turn; do not join pieces from different turns; do not paraphrase, fix spelling or add punctuation. Differences in whitespace and in curly versus straight quotes are tolerated, nothing else is. Keep a quote short, usually one clause. `## CODE CONTEXT`, `## CODE NOTES` and `## FACTS` are NOT part of the session: never quote them.
Every `turn` you give (in `history`, `evidence` and findings) must be a turn id that exists in `## SESSION`, written as in the session (`T14`).

## Rules for `functions`
1. Answer every label listed in `## RESPONSE` exactly once, using the label as `fn`. Do not answer a label that is not listed. Do not use the function name as `fn`.
2. `reason`: one or two plain sentences saying why this function changed. Name what changed in behaviour, not the code you can see. For `deleted`, say why it was removed. For `added`, say what it is for.
3. `driver`, exactly one of:
   - `user_asked`: the person asked for this. You MUST give at least one `evidence` quote taken from a `user` turn.
   - `agent_decided`: the agent chose it to solve the task, to fix an error, or to stay consistent with other changes.
   - `not_stated`: the session does not explain why this function changed.
4. `history`: the steps it took to get there, only when there were several attempts, a failure or a refinement. Each item is `{"turn": "T14", "text": "Tried wrapping send()"}` with a short text of your own words. Use `[]` when it was a single straightforward edit.
5. `evidence`: at least one quote that supports the reason, unless `driver` is `not_stated`, in which case use `[]`.
6. `confidence`: `high` (the session says it directly), `medium` (strongly implied), `low` (you are inferring).
7. If the session gives no reason: `driver` is `not_stated`, `reason` is exactly `"No reason found in the session"`, `history` and `evidence` are `[]`, `confidence` is `low`. Never guess a reason from the code alone.
8. For `source: outside_session`, answer `not_stated` unless a turn in the session clearly explains the change and you can quote it.
9. A function the agent edited several times: judge by the final result. Mention the earlier attempts in `history`.

## Rules for `session_review`
List only what the session itself shows. Do NOT review the code or the diff. Each finding needs `kind`, `finding` (one sentence), `functions` (labels such as `F2`, or `[]` if it concerns no single function) and at least one `evidence` quote. If you find nothing, return `[]`. Kinds:
- `claim_not_backed`: the agent claims something (for example "added tests for both clients") that `## FACTS` or the transcript contradicts.
- `test_failed_ignored`: a test failed and the agent went on without fixing it or saying so.
- `not_tested_after_change`: no test ran after the final edit. This must agree with `## FACTS`; if the facts say a test ran after the final edit, do not report it.
- `request_not_done`: something the person explicitly asked for is missing from the changed functions.
- `check_weakened`: a test was skipped, an assertion loosened, or a broad exception handler added to make a check pass.
- `dead_end`: an approach was tried and then reverted or abandoned.

`summary`: two or three sentences: what the session set out to do and what was done.

## Output format
Reply with exactly one JSON object and nothing else: no markdown fences, no text before or after, no comments. Use double quotes, no trailing commas, and escape quotes and line breaks inside strings (`\"` and `\n`). Use `[]` for an empty list, never `null`. Do not add fields. Enumerated fields take exactly the allowed lowercase values.

Fields:

| field | type | meaning |
|---|---|---|
| `summary` | string | 2 to 3 sentences about the whole session |
| `functions` | list | one item per label in `## RESPONSE` |
| `functions[].fn` | string | the label, `F1` ... |
| `functions[].reason` | string | 1 to 2 sentences |
| `functions[].driver` | `user_asked` \| `agent_decided` \| `not_stated` | who caused the change |
| `functions[].history` | list of `{turn, text}` | steps, or `[]` |
| `functions[].evidence` | list of `{turn, quote}` | verbatim quotes, or `[]` for `not_stated` |
| `functions[].confidence` | `high` \| `medium` \| `low` | how sure you are |
| `session_review` | list | problems the session shows, or `[]` |
| `session_review[].kind` | one of the six kinds above | what kind of problem |
| `session_review[].finding` | string | one sentence |
| `session_review[].functions` | list of labels | functions concerned, or `[]` |
| `session_review[].evidence` | list of `{turn, quote}` | at least one verbatim quote |

Example (the values are only an illustration of the shape):

```json
{
  "summary": "The person asked for retries on the client. The agent added a retry loop in send, then fixed a failing test.",
  "functions": [
    {
      "fn": "F1",
      "reason": "Adds the retry loop the person asked for around the request.",
      "driver": "user_asked",
      "history": [
        {"turn": "T6", "text": "First tried retrying in the caller"},
        {"turn": "T12", "text": "Moved the loop into send after a test failed"}
      ],
      "evidence": [
        {"turn": "T1", "quote": "retry failed requests up to three times"},
        {"turn": "T12", "quote": "Move the retry loop into send"}
      ],
      "confidence": "high"
    },
    {
      "fn": "F2",
      "reason": "No reason found in the session",
      "driver": "not_stated",
      "history": [],
      "evidence": [],
      "confidence": "low"
    }
  ],
  "session_review": [
    {
      "kind": "claim_not_backed",
      "finding": "The agent says it added tests for both clients, but only one test ran.",
      "functions": ["F2"],
      "evidence": [{"turn": "T20", "quote": "added tests for both clients"}]
    }
  ]
}
```

JSON Schema of the answer (authoritative; your reply must validate against it):

```json
{{JSON_SCHEMA}}
```

## Before you answer
Check each item: every label in `## RESPONSE` appears once in `functions`; every `turn` exists in `## SESSION`; every quote is copied from the turn it names; every `user_asked` has a quote from a `user` turn; nothing contradicts `## FACTS`; the reply is one JSON object with no text around it.
