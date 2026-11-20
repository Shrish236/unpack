# Unpack: Per-Function Reason Explanation (Prompt v1)

You are explaining why an AI agent made each code change, using ONLY the session provided.

## Instructions
1. For each function F#:
   - Provide a 1-to-2 sentence reason describing why the change was made.
   - Specify who drove the change: `user_asked`, `agent_decided`, or `not_stated`.
   - Summarize the history if there were several attempts or failed test iterations.
   - Provide at least one verbatim quote from a turn as evidence with its turn ID.
2. If the session gives no reason, set driver to `not_stated` and reason to "No reason found in the session". Do not guess.
3. For functions marked `outside_session`, return `not_stated` unless a turn clearly explains them.
4. Do not contradict the FACTS section.
5. Review the session for specific issues:
   - `claim_not_backed`: Agent claims something (e.g. "added tests") contradicted by facts.
   - `test_failed_ignored`: A test failure occurred and was not addressed.
   - `not_tested_after_change`: No test run took place after the final edit.
   - `request_not_done`: A user request was unfulfilled in the diff.
   - `check_weakened`: Test assertions were relaxed or skipped.
   - `dead_end`: An approach was tried and reverted.

Every quote must match verbatim character for character.
