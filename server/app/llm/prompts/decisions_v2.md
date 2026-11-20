# Unpack: Decision Extraction (Prompt v2)

You read one coding-agent session and extract the DECISIONS in it, using ONLY the session provided.
A decision is a point where a choice was made that shaped the code: which design, which dependency, how to retry, what to test, what is in scope.

## Rules
1. `actor`:
   - `human`: the person changed what the agent was doing or planned to do. `turn` MUST be a `user` turn, and `quote` MUST be copied character for character from it.
   - `agent`: the agent chose between real alternatives, or chose something the user did not ask for. `turn` is an assistant, thought, plan or edit turn. `quote` is copied character for character from that turn.
2. For `human`, `kind` is exactly one of:
   - `redirect`: the user told the agent to do something different from what it was doing.
   - `reject`: the user refused something the agent proposed or did.
   - `requirement`: the user added a requirement the original request did not state.
   - `discussion`: the user chose between options the agent offered.
   For `agent`, `kind` is `choice`.
3. `type`: one of `architecture`, `design`, `dependency`, `retries`, `test`, `scope`, `other`.
4. `proposal` is what was on the table (1 sentence). `choice` is what was decided (1 sentence).
5. `statement`: for a human decision, write the correction as a short, general, reusable rule that does not mention this task, e.g. "Do not add a new runtime dependency without approval". The same correction in different sessions must produce nearly the same statement. For agent decisions use "".
6. `rule_id`: if a rule in `## STEERING` applies to the decision, give its id (S1, S2 ...). `rule_followed` is true if the agent's action followed that rule, false if it went against it. Use null for both when no rule applies. Never invent a rule id.
7. Do NOT list tool calls the human refused at the permission prompt; those are already recorded (`## REFUSED TOOL CALLS`).
8. Do not report a user message that only asks the agent to start, continue or explain.
9. `highlights`: up to 4 items, only what is visible in the session. `went_right` is something that worked and was verified (a test passing after a fix, a requirement met). `went_wrong` is a mistake, a dead end, an ignored failure, or a claim the session does not back. Each needs `turn` and a verbatim `quote` from that turn.
10. If the session has no decisions, return empty lists. Do not guess.
11. `## CHANGED CODE` and `## SIGNALS` describe what the session produced: the functions that changed (with callers and test reach), flags such as a new dependency or a skipped test, and how many attempts it took. Use them to judge a decision's `type` and whether it was in scope. They are context only: every `quote` must still be copied from `## SESSION`.

## Output JSON Schema
Return valid JSON only:
```json
{
  "decisions": [
    {
      "turn": "T7", "actor": "human", "kind": "reject", "type": "dependency",
      "proposal": "Agent planned to add the tenacity package for retries",
      "choice": "Write a small retry loop with the standard library",
      "statement": "Do not add a new runtime dependency for small helpers",
      "quote": "no, don't add tenacity",
      "rule_id": "S3", "rule_followed": false
    }
  ],
  "highlights": [
    {"kind": "went_right", "text": "Tests passed after the final edit", "turn": "T31", "quote": "5 passed"}
  ]
}
```
