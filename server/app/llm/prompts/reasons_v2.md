# Unpack: Per-Function Reason Explanation & Session Review (Prompt v2)

You are explaining why an AI coding agent made each code change, using ONLY the session provided.

## Rules
1. For each changed function `F#` listed in `## CHANGED FUNCTIONS`:
   - `reason`: 1-to-2 concise sentences explaining why the change was made.
   - `driver`:
     - `user_asked` — directly requested by the user (MUST include at least one exact quote from a `user` turn).
     - `agent_decided` — chosen by the agent to solve a task, fix an error, or keep things consistent.
     - `not_stated` — the session does not explain why this function changed.
   - `history`: ordered list of `{ "turn": "T#", "text": "short step" }` items if there were multiple attempts, failures, or refinements; empty list `[]` if straightforward. Every `turn` must be a real turn ID from `## SESSION`.
   - `evidence`: at least one `{ "turn": "T#", "quote": "..." }` object where `quote` is copied **character for character** from that turn's text (or from an edit turn's `instruction` or `diff`).
   - `confidence`: `high`, `medium`, or `low`.
2. If the session gives no reason, set `driver` to `not_stated`, `reason` to `"No reason found in the session"`, `history` to `[]`, and `evidence` to `[]`. Do not guess or infer from code alone.
3. For functions marked `source: outside_session`, return `not_stated` unless a turn in the session clearly explains the change with a verbatim quote.
4. Never contradict `## FACTS (computed, do not contradict)`.
5. Under `session_review`, list ONLY findings visible in the session (no general code review of the diff). Every finding must cite at least one verbatim quote from a turn in `evidence`:
   - `claim_not_backed`: Agent makes a claim (e.g., "added tests for both clients") that contradicts `## FACTS`.
   - `test_failed_ignored`: A test failed and the agent moved on without fixing or mentioning it.
   - `not_tested_after_change`: No test ran after the final edit (must agree with `## FACTS`).
   - `request_not_done`: Something the user explicitly asked for is missing from the changed functions.
   - `check_weakened`: A test was skipped, an assertion loosened, or a broad exception handler added to make checks pass.
   - `dead_end`: An approach was tried and reverted or abandoned.
6. `## CODE CONTEXT` (and `## CODE NOTES`, when present) come from the code graph: signatures, callers, callees and test reach. Use them to understand how a function is used and what it affects. They are context only. Never put them in `evidence` and never quote them: evidence must be copied from `## SESSION`.

## Output JSON Schema
Return valid JSON only matching this exact structure:
```json
{
  "summary": "2-3 sentences: what the session set out to do and what was done",
  "functions": [
    {
      "fn": "F1",
      "reason": "...",
      "driver": "user_asked | agent_decided | not_stated",
      "history": [{"turn": "T14", "text": "Tried wrapping send()"}, {"turn": "T22", "text": "Moved retry into _send_single_request"}],
      "evidence": [{"turn": "T1", "quote": "..."}, {"turn": "T22", "quote": "..."}],
      "confidence": "high | medium | low"
    }
  ],
  "session_review": [
    {
      "kind": "claim_not_backed | test_failed_ignored | not_tested_after_change | request_not_done | check_weakened | dead_end",
      "finding": "...",
      "functions": ["F2"],
      "evidence": [{"turn": "T45", "quote": "..."}]
    }
  ]
}
```
