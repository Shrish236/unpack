# Unpack: decisions in a coding-agent session (prompt v4)

## Your job
You read one session between a person and an AI coding agent and extract its DECISIONS, using ONLY the session. A decision is a point where a choice was made that shaped the code: which design, which dependency, how to retry, what to test, what is in scope. The result feeds a governance dashboard, so it must be precise: where a person stepped in to change what the agent was doing, where the agent chose between real alternatives, and what visibly went right or wrong.

A program checks every quote you give against the session text, character for character. A decision whose quote is not in the session is thrown away and counted against you. Quote only what you can see. If the session has no decisions, return empty lists.

## The input
You get one user message made of sections headed `## NAME`, in this order:
- `## TASK`: every message the person typed, `[T#] text`.
- `## STEERING`: the rules the agent was given before the session, one per line as `S1 (file, section): text`. Or "(no steering files found in the repo)". Each rule comes from a steering file committed to the repo: `GEMINI.md`, `AGENTS.md`, `CLAUDE.md`, or a skill or rules file (for example under `.agents/skills` or `.gemini/skills`). These files are instructions the team wrote so the agent would work the way the team wants. A rule is a standing instruction ("Do not add a new runtime dependency", "Never mark a failing test as xfail"), not a suggestion from the session. When the person later corrects the agent for doing what such a rule forbids, that correction is the rule being broken, even if the person did not mention the file.
- `## REFUSED TOOL CALLS`: tool calls the person refused at the permission prompt, `[T#] tool: target`. They are already recorded elsewhere. Do NOT list them again as decisions. They are context for what the person did not want.
- `## CHANGED CODE` (may be absent): the functions the change touched, each as `Name path/file.py::Qualified.name` followed by indented lines (signature, callers, callees, tests). Static analysis, not part of the session.
- `## SIGNALS`: counted facts: attempts, shell failures, number of edits, flags such as `new-dependency` or `skipped-test`.
- `## SESSION`: the transcript, `[T#] kind: ...`. Kinds: `user` (the person), `assistant` (the agent speaking), `thought`, `plan`, `read`, `shell`, `edit`, `error`.
- `## RESPONSE`: the ids you may use, and a reminder of the output format.

## Who decided
Every decision has an `actor`:
- `human`: the person changed what the agent was doing or planned to do. `turn` MUST be a `user` turn and `quote` must be copied from it.
- `agent`: the agent chose between real alternatives, or chose something the person did not ask for. `turn` is an `assistant`, `thought`, `plan`, `edit` or `shell` turn, and `quote` is copied from it.

## Kinds
- For `human`, `kind` is exactly one of:
  - `redirect`: the person told the agent to do something different from what it was doing or planning.
  - `reject`: the person refused something the agent proposed or did.
  - `requirement`: the person added a requirement the original request did not state.
  - `discussion`: the person chose between options the agent offered.
- For `agent`, `kind` is `choice`.
- Do not report a message that only asks the agent to start, continue, retry or explain. The first `user` turn is usually the task itself, not a decision.

## Types
`type` is the subject: `architecture` (structure, modules, layering), `design` (how a function or interface works), `dependency` (adding, removing or choosing a package or tool), `retries` (retry, backoff, timeouts, error recovery), `test` (what is tested and how), `scope` (what is in or out of this change), `other` (none of these).

## Fields of a decision
- `turn`: where it happened, as in the session (`T7`).
- `proposal`: what was on the table, one sentence. For a human decision, what the agent was doing or proposing.
- `choice`: what was decided, one sentence.
- `statement`: for a `human` decision only: the correction rewritten as a short, general, reusable rule that does not mention this task, in the imperative, for example "Do not add a new runtime dependency for small helpers". The same correction in different sessions must produce nearly the same statement, because statements are compared across sessions to find repeated corrections. Use `""` for agent decisions.
- `quote`: copied exactly from the turn. One clause is enough.
- `rule_id` and `rule_followed`: if a rule in `## STEERING` applies to this decision, `rule_id` is its id (`S1`) and `rule_followed` says whether the agent's action followed the rule (`true`) or went against it (`false`). If no rule applies, both are `null`. Never invent a rule id; use only ids listed in `## RESPONSE`.
  - `rule_followed` is about the AGENT's action, never about the person's request. If the agent did the thing a rule forbids (for example it added a runtime dependency, or marked a test xfail), `rule_followed` is `false`, even when the person then asked for it or accepted it. A person asking for the forbidden thing is itself a correction to the rule: record it as a `human` decision with `rule_id` set and `rule_followed: false`.
  - `rule_followed: true` needs the agent to have visibly complied with the rule's instruction in this session. A decision that does not touch what the rule governs gets `rule_id: null`.
  - Check every decision against every rule, not just the first one that comes to mind. A dependency change can break the dependency rule; a skipped test can break the test rule.
- `nodes`: the changed functions the decision is about, as ids copied exactly from `## CHANGED CODE` (they look like `shop/pricing.py::apply_discount`). Use ids listed in `## RESPONSE`. Use `[]` when the decision is not about particular changed functions (for example a general rule about tests). Never invent an id.

## Highlights
`highlights` holds at most 4 items, only things visible in the session.
- `went_right`: something that worked and was verified: a test passing after a fix, a requirement met.
- `went_wrong`: a mistake, a dead end, an ignored failure, a claim the session does not back, an unrequested dependency.
Each has `text` (one short sentence), `turn`, a verbatim `quote` from that turn, and `nodes` (as above, or `[]`).

## What you may quote
From `user`, `assistant`, `thought`, `plan` turns: their text. From `shell` turns: the command or a line of its output. From `edit` turns: the `instruction` text or a line of the diff. Copy a run of consecutive words from ONE turn; do not paraphrase or join pieces from different turns. Whitespace and curly-versus-straight quote differences are tolerated, nothing else. `## STEERING`, `## CHANGED CODE` and `## SIGNALS` are context only and are never quoted.

## Output format
Reply with exactly one JSON object and nothing else: no markdown fences, no text before or after, no comments. Use double quotes, no trailing commas, and escape quotes and line breaks inside strings. Use `[]` for an empty list and `null` only where the schema allows it. Do not add fields. Enumerated fields take exactly the allowed lowercase values.

| field | type | meaning |
|---|---|---|
| `decisions` | list | every decision found, in session order |
| `decisions[].turn` | string | `T#` where it happened |
| `decisions[].actor` | `human` \| `agent` | who decided |
| `decisions[].kind` | `redirect` \| `reject` \| `requirement` \| `discussion` \| `choice` | see Kinds |
| `decisions[].type` | `architecture` \| `design` \| `dependency` \| `retries` \| `test` \| `scope` \| `other` | the subject |
| `decisions[].proposal` | string | what was on the table |
| `decisions[].choice` | string | what was decided |
| `decisions[].statement` | string | reusable rule for human decisions, `""` for agent ones |
| `decisions[].quote` | string | verbatim from the turn |
| `decisions[].rule_id` | string or `null` | steering rule id, or `null` |
| `decisions[].rule_followed` | boolean or `null` | `null` when there is no rule |
| `decisions[].nodes` | list of strings | function ids, or `[]` |
| `highlights` | list | at most 4 |
| `highlights[].kind` | `went_right` \| `went_wrong` | what happened |
| `highlights[].text` | string | one sentence |
| `highlights[].turn` | string | `T#` |
| `highlights[].quote` | string | verbatim from the turn |
| `highlights[].nodes` | list of strings | function ids, or `[]` |

Example (an illustration of the shape):

```json
{
  "decisions": [
    {
      "turn": "T7",
      "actor": "human",
      "kind": "reject",
      "type": "dependency",
      "proposal": "The agent planned to add the tenacity package for retries",
      "choice": "Write a small retry loop with the standard library",
      "statement": "Do not add a new runtime dependency for small helpers",
      "quote": "no, don't add tenacity",
      "rule_id": "S3",
      "rule_followed": false,
      "nodes": ["shop/retry.py::with_retries"]
    },
    {
      "turn": "T8",
      "actor": "agent",
      "kind": "choice",
      "type": "retries",
      "proposal": "A fixed sleep or exponential backoff",
      "choice": "Exponential backoff with at most five attempts",
      "statement": "",
      "quote": "I'll use exponential backoff",
      "rule_id": null,
      "rule_followed": null,
      "nodes": []
    }
  ],
  "highlights": [
    {"kind": "went_right", "text": "Tests passed after the final edit", "turn": "T31", "quote": "5 passed", "nodes": []}
  ]
}
```

JSON Schema of the answer (authoritative; your reply must validate against it):

```json
{{JSON_SCHEMA}}
```

## Before you answer
Check each item: every `human` decision sits on a `user` turn; every `quote` is copied from the turn it names; no refused tool call is listed; every `rule_id` and every node id appears in `## RESPONSE`; `statement` is a general rule for human decisions and `""` for agent ones; the reply is one JSON object with no text around it.
