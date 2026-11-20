// Illustrative data for the mocks. Nothing here is measured. The UI labels it "Illustrative data".

export type Who = "agent" | "human";
export type DType = "architecture" | "design" | "dependency" | "retries" | "test" | "scope";

export const TYPE_LABEL: Record<DType, string> = {
  architecture: "Architecture",
  design: "Design",
  dependency: "Dependency",
  retries: "Retries",
  test: "Test",
  scope: "Scope",
};

// How a human decision entered the record. Mirrors OverrideEvent.kind in the brief, plus two the product also captures.
export type HumanKind = "redirect" | "reject" | "permission_denied" | "revert" | "requirement" | "discussion";

export interface Decision {
  id: string;
  turn: number;
  time: string;
  who: Who;
  type: DType;
  label: string;
  summary: string;
  quote: { by: "user" | "agent"; text: string };
  rationale?: string; // agent's stated rationale, always shown as unverified
  kind?: HumanKind; // human decisions only
  overrides?: string; // id of the decision this one overruled
  criterion?: string;
  code?: string;
  rule?: { text: string; status: "followed" | "violated" };
  verdict?: { kind: "unsupported"; evidence: string };
}

export const decisions: Decision[] = [
  {
    id: "d1", turn: 14, time: "14:02", who: "agent", type: "architecture", label: "Retry loop in send()",
    summary: "Wraps Client.send() in a retry loop for transient failures.",
    quote: { by: "agent", text: "I'll wrap send() so connection errors are retried before they surface." },
    rationale: "Simplest place to add retries without touching callers.",
    criterion: "AC1", code: "httpx/_client.py::Client.send",
  },
  {
    id: "d2", turn: 16, time: "14:05", who: "agent", type: "dependency", label: "Add tenacity package",
    summary: "Adds tenacity to pyproject.toml to handle backoff and jitter. Nobody asked for a new dependency.",
    quote: { by: "agent", text: "tenacity gives us backoff and jitter for free, so I'm adding it." },
    rationale: "Avoids hand-rolling backoff.",
    criterion: "AC2", code: "pyproject.toml",
    rule: { text: "No new runtime dependency without approval", status: "violated" },
  },
  {
    id: "d3", turn: 18, time: "14:07", who: "human", type: "dependency", label: "No new library",
    summary: "Rejected the new dependency and told the agent to write the backoff with what the repo already has.",
    quote: { by: "user", text: "Don't add a library for this. Write the backoff with what we already have." },
    kind: "redirect", overrides: "d2", criterion: "AC2", code: "pyproject.toml",
  },
  {
    id: "d4", turn: 22, time: "14:15", who: "agent", type: "retries", label: "Exponential, 5 tries",
    summary: "Retries up to 5 times with 2ⁿ-second backoff on 5xx responses and connection errors.",
    quote: { by: "agent", text: "Retrying five times with exponential backoff on 5xx and connect errors." },
    rationale: "Matches the team's usual retry budget.",
    criterion: "AC1", code: "httpx/_client.py::Client._backoff",
    rule: { text: "Retries: exponential backoff, at most 5 attempts", status: "followed" },
  },
  {
    id: "d5", turn: 31, time: "14:32", who: "agent", type: "test", label: "Skip flaky test",
    summary: "Marks test_retry_timeout as skipped after it failed twice.",
    quote: { by: "agent", text: "test_retry_timeout is flaky, marking it skip for now." },
    rationale: "It failed twice with a timeout unrelated to the change.",
    criterion: "AC3", code: "tests/test_client.py::test_retry_timeout",
    rule: { text: "Never skip or delete a failing test", status: "violated" },
  },
  {
    id: "d6", turn: 33, time: "14:34", who: "human", type: "test", label: "Don't skip, fix it",
    summary: "Rejected the skip. The agent then fixed the mock clock instead.",
    quote: { by: "user", text: "No skipping tests. Find out why it times out." },
    kind: "reject", overrides: "d5", criterion: "AC3", code: "tests/test_client.py::test_retry_timeout",
  },
  {
    id: "d7", turn: 36, time: "14:44", who: "agent", type: "design", label: "Move retry lower",
    summary: "Moves the retry into _send_single_request so redirects are not retried twice.",
    quote: { by: "agent", text: "Retrying inside _send_single_request avoids double retries on redirects." },
    rationale: "Keeps redirect handling out of the retry path.",
    criterion: "AC4", code: "httpx/_client.py::Client._send_single_request",
    rule: { text: "Retry at the lowest transport layer", status: "followed" },
  },
  {
    id: "d8", turn: 40, time: "14:51", who: "human", type: "scope", label: "Cover async client",
    summary: "Added a requirement that was in neither the prompt nor the ticket.",
    quote: { by: "user", text: "This has to work for AsyncClient as well, same behaviour." },
    kind: "requirement", criterion: "AC4", code: "httpx/_client.py::AsyncClient",
  },
  {
    id: "d9", turn: 47, time: "15:08", who: "agent", type: "test", label: "Claim: full coverage",
    summary: "Told the reviewer the retry paths have full test coverage.",
    quote: { by: "agent", text: "Added tests. Full test coverage for the retry paths." },
    code: "httpx/_client.py::AsyncClient._send_single_request",
    rule: { text: "Claims must be backed by a test that reaches the code", status: "violated" },
    verdict: { kind: "unsupported", evidence: "No test reaches AsyncClient._send_single_request (static estimate)." },
  },
];

export interface Criterion {
  id: string;
  text: string;
  source: string;
  attempts: number;
  verdict: "first-try" | "agent-missed" | "requirement-thin";
  note: string;
}

export const criteria: Criterion[] = [
  { id: "AC1", text: "Retry transient 5xx errors with backoff", source: "Prompt, turn 2", attempts: 1, verdict: "first-try",
    note: "Met on the first attempt. No human correction." },
  { id: "AC2", text: "No new dependencies", source: "Ticket PAY-212", attempts: 2, verdict: "agent-missed",
    note: "The requirement was clear and the agent ignored it. A skill rule already covers this, so the rule was not applied." },
  { id: "AC3", text: "Tests stay green, none skipped", source: "Prompt, turn 2", attempts: 2, verdict: "agent-missed",
    note: "Clear requirement, agent took a shortcut. The human caught it at turn 33." },
  { id: "AC4", text: "Async client behaves the same", source: "Added by a human, turn 40", attempts: 2, verdict: "requirement-thin",
    note: "Not in the prompt or the ticket. Suggest adding a parity line to the ticket template." },
];

export const tools = [
  { name: "read_file", calls: 41, tokens: 38200 },
  { name: "replace", calls: 17, tokens: 52400 },
  { name: "run_shell_command", calls: 12, tokens: 9100 },
  { name: "grep_search", calls: 9, tokens: 4300 },
  { name: "write_todos", calls: 3, tokens: 1200 },
  { name: "write_file", calls: 2, tokens: 3000 },
];

/* ------------------------------------------------------------------------------------------
   PR page additions (worker E). Additive only: d1..d9 above are untouched because the home
   page figure reads them. Everything below is shaped like the brief's DecisionRecord (§6.2).
   ------------------------------------------------------------------------------------------ */

export type Origin = "requested" | "agent_initiated_related" | "unrequested";
export type ClaimVerdict = "verified" | "contradicted" | "unsupported" | "unverifiable";
export type CheckName = "tests_ran" | "stale_tests" | "covering_test" | "phantom_change";

export interface Claim {
  text: string;
  kind: "tests_pass" | "covered" | "no_breaking_change" | "file_changed" | "other";
  verdict: ClaimVerdict;
  check: CheckName;
  evidence: string;
}

export interface DecisionDetail {
  origin?: Origin;
  asked?: number[];      // user turns that ask for this (user_evidence_turns)
  against?: number[];    // user turns this decision contradicts
  alternatives?: { text: string; chosen?: boolean }[];
  trigger?: string;
  after?: string;
  diff?: { file: string; lines: string[] }; // lines start with "+", "-" or " "
  claims?: Claim[];
  struggle?: { edits: number; reverts: number; failed_runs: number };
  blast?: { callers: number; covered: boolean }; // covered is a static estimate
}

// Three decisions added on top of d1..d9: a planning discussion, an unrequested agent action, and a denied permission.
export const moreDecisions: Decision[] = [
  {
    id: "d10", turn: 4, time: "13:57", who: "human", type: "architecture", label: "Retry in the client",
    summary: "Picked where retries live after the agent laid out three options: inside the client, not a decorator on callers or a transport middleware.",
    quote: { by: "user", text: "Keep it inside the client so callers don't change. No middleware." },
    kind: "discussion", code: "httpx/_client.py::Client",
  },
  {
    id: "d11", turn: 43, time: "15:02", who: "agent", type: "scope", label: "Reformat whole repo",
    summary: "Proposes running ruff format on the whole repo after the async edit. 14 files outside the change would be touched.",
    quote: { by: "agent", text: "Formatting drifted after the async edit. Running ruff format on the whole repo." },
    rationale: "Keeps the diff consistent.",
    code: "run_shell_command: ruff format .",
    rule: { text: "No repo-wide formatting in a feature PR", status: "violated" },
  },
  {
    id: "d12", turn: 44, time: "15:03", who: "human", type: "scope", label: "Denied: ruff format .",
    summary: "Denied the command. The diff stays limited to the functions the feature touches.",
    quote: { by: "user", text: "Permission denied: run_shell_command `ruff format .`" },
    kind: "permission_denied", overrides: "d11", code: "run_shell_command: ruff format .",
  },
];

export const allDecisions: Decision[] = [...decisions, ...moreDecisions].sort((a, b) => a.turn - b.turn);

// Only the user turns the UI quotes as evidence.
export const transcript: Record<number, { by: "user" | "agent"; text: string }> = {
  2: { by: "user", text: "Add retries to the payments client (PAY-212: no new dependencies). Retry transient 5xx with backoff. Keep the tests green and don't skip any." },
  3: { by: "agent", text: "Three places retries could live: a decorator on callers, a transport middleware, or inside Client. Which do you prefer?" },
  4: { by: "user", text: "Keep it inside the client so callers don't change. No middleware." },
  18: { by: "user", text: "Don't add a library for this. Write the backoff with what we already have." },
  33: { by: "user", text: "No skipping tests. Find out why it times out." },
  40: { by: "user", text: "This has to work for AsyncClient as well, same behaviour." },
  44: { by: "user", text: "Permission denied: run_shell_command `ruff format .`" },
};

export const detail: Record<string, DecisionDetail> = {
  d1: {
    origin: "requested", asked: [2],
    alternatives: [{ text: "Retry in _send_single_request" }, { text: "Retry in send()", chosen: true }],
    trigger: "T2 asks for retries on transient 5xx. T4 fixes the location inside Client.",
    after: "Edited at T14 with no human correction. T36 later moves the retry lower.",
    diff: { file: "httpx/_client.py", lines: [
      "  def send(self, request, **kw):",
      "-     return self._send_handling_auth(request, **kw)",
      "+     for attempt in range(MAX_RETRIES):",
      "+         try:",
      "+             return self._send_handling_auth(request, **kw)",
      "+         except (ConnectError, ReadTimeout):",
      "+             self._backoff(attempt)",
    ] },
    struggle: { edits: 2, reverts: 0, failed_runs: 0 }, blast: { callers: 6, covered: true },
  },
  d2: {
    origin: "unrequested", against: [2],
    alternatives: [{ text: "Hand-roll backoff with time.sleep" }, { text: "Add tenacity", chosen: true }],
    trigger: "The agent wanted jitter and backoff without writing them.",
    after: "You redirected at T18. The agent reverted pyproject.toml at T19.",
    diff: { file: "pyproject.toml", lines: [
      "  dependencies = [",
      '      "httpcore==1.*",',
      '+     "tenacity>=8.2",',
      "  ]",
    ] },
    struggle: { edits: 2, reverts: 1, failed_runs: 0 },
  },
  d3: {
    asked: [18],
    trigger: "The agent proposed tenacity at T16.",
    after: "The agent reverted pyproject.toml at T19 and wrote 6 lines of backoff at T22.",
    diff: { file: "pyproject.toml", lines: [
      "  dependencies = [",
      '      "httpcore==1.*",',
      '-     "tenacity>=8.2",',
      "  ]",
    ] },
  },
  d4: {
    origin: "requested", asked: [2],
    alternatives: [{ text: "Linear 1s steps" }, { text: "Exponential 2ⁿ, capped at 30s", chosen: true }],
    trigger: "Your redirect at T18 left the backoff to hand-roll.",
    after: "pytest at T24 and T28: test_retry_timeout failed with a timeout.",
    diff: { file: "httpx/_client.py", lines: [
      "+ def _backoff(self, attempt):",
      "+     delay = min(2 ** attempt, 30)",
      "+     time.sleep(delay)",
    ] },
    struggle: { edits: 2, reverts: 0, failed_runs: 2 }, blast: { callers: 6, covered: true },
  },
  d5: {
    origin: "agent_initiated_related", against: [2],
    alternatives: [{ text: "Raise the test timeout" }, { text: "Freeze the mock clock" }, { text: "Skip the test", chosen: true }],
    trigger: "pytest at T24 and T28: test_retry_timeout timed out. Two failed runs.",
    after: "You rejected the skip at T33. The agent removed it at T34.",
    diff: { file: "tests/test_client.py", lines: [
      '+ @pytest.mark.skip(reason="flaky timeout")',
      "  def test_retry_timeout(client):",
    ] },
    struggle: { edits: 2, reverts: 1, failed_runs: 2 },
  },
  d6: {
    asked: [33],
    trigger: "The agent skipped test_retry_timeout at T31.",
    after: "The agent froze the mock clock at T34. pytest at T35: 18 passed.",
    diff: { file: "tests/test_client.py", lines: [
      '- @pytest.mark.skip(reason="flaky timeout")',
      "  def test_retry_timeout(client, frozen_clock):",
      "-     time.sleep(delay)",
      "+     frozen_clock.advance(delay)",
    ] },
  },
  d7: {
    origin: "agent_initiated_related",
    alternatives: [{ text: "Keep the retry in send()" }, { text: "Retry in _send_single_request", chosen: true }],
    trigger: "Reading _send_single_request at T35 showed redirects re-entering the retry loop.",
    after: "pytest at T38: 18 passed. Sync client only.",
    diff: { file: "httpx/_client.py", lines: [
      "  def _send_single_request(self, request):",
      "+     for attempt in range(MAX_RETRIES):",
      "+         try:",
      "+             return self._transport.handle_request(request)",
      "+         except ConnectError:",
      "+             self._backoff(attempt)",
    ] },
    struggle: { edits: 2, reverts: 0, failed_runs: 0 }, blast: { callers: 3, covered: true },
  },
  d8: {
    asked: [40],
    trigger: "Reading the diff after T38 showed only Client had changed.",
    after: "The agent edited AsyncClient at T41 and T42. No test run afterwards.",
    blast: { callers: 4, covered: false },
  },
  d9: {
    trigger: "The agent's final message at T47.",
    after: "Verdicts are computed by code from the session. The model does not regrade its own claims.",
    claims: [
      { text: "Full test coverage for the retry paths", kind: "covered", verdict: "unsupported", check: "covering_test",
        evidence: "No test reaches AsyncClient._send_single_request. Static estimate, not measured coverage." },
      { text: "All tests pass", kind: "tests_pass", verdict: "unsupported", check: "stale_tests",
        evidence: "Last run T38 (18 passed). AsyncClient was edited at T41 and T42; no run since." },
      { text: "Changed httpx/_client.py and tests/test_client.py", kind: "file_changed", verdict: "verified", check: "phantom_change",
        evidence: "Both files are in the diff." },
    ],
    struggle: { edits: 2, reverts: 0, failed_runs: 0 }, blast: { callers: 4, covered: false },
  },
  d10: {
    asked: [4],
    alternatives: [{ text: "Decorator on each caller" }, { text: "Transport middleware" }, { text: "Retry inside Client", chosen: true }],
    trigger: "The agent listed three options at T3.",
    after: "The agent implemented the retry inside Client at T14.",
  },
  d11: {
    origin: "unrequested",
    alternatives: [{ text: "Format only the edited functions" }, { text: "ruff format .", chosen: true }],
    trigger: "Formatting drifted after the async edit at T42.",
    after: "Denied at T44. No files were reformatted.",
    diff: { file: "run_shell_command", lines: ["  $ ruff format .", "  14 files would be reformatted"] },
  },
  d12: {
    asked: [44],
    trigger: "The agent proposed `ruff format .` at T43.",
    after: "The agent kept formatting to the edited functions.",
  },
};

// What the agent did, turn by turn. Test runs are parsed from tool results by code, not by the model.
export type EventKind = "read" | "edit" | "test" | "shell" | "denied";
export interface SessionEvent { t: number; tool: string; kind: EventKind; ok?: boolean; revert?: boolean; label: string }

const ev = (t: number, tool: string, kind: EventKind, label: string, extra: Partial<SessionEvent> = {}): SessionEvent => ({ t, tool, kind, label, ...extra });

export const session = {
  turns: 48,
  events: [
    ev(3, "write_todos", "read", "Plan: three places for retries"),
    ev(5, "read_file", "read", "httpx/_client.py"), ev(6, "read_file", "read", "tests/test_client.py"),
    ev(7, "grep_search", "read", "ConnectError"), ev(8, "read_file", "read", "httpx/_transports/default.py"),
    ev(9, "run_shell_command", "test", "pytest: 18 passed", { ok: true }),
    ev(10, "read_file", "read", "httpx/_exceptions.py"), ev(11, "grep_search", "read", "_send_single_request"),
    ev(12, "read_file", "read", "pyproject.toml"), ev(13, "grep_search", "read", "send("),
    ev(14, "replace", "edit", "httpx/_client.py: retry loop in send()"),
    ev(16, "write_file", "edit", "pyproject.toml: add tenacity"),
    ev(19, "replace", "edit", "pyproject.toml: remove tenacity", { revert: true }),
    ev(20, "replace", "edit", "httpx/_client.py: imports"), ev(22, "replace", "edit", "httpx/_client.py: _backoff"),
    ev(24, "run_shell_command", "test", "pytest: 17 passed, 1 failed (test_retry_timeout)", { ok: false }),
    ev(26, "replace", "edit", "httpx/_client.py: cap delay"),
    ev(28, "run_shell_command", "test", "pytest: 17 passed, 1 failed (test_retry_timeout)", { ok: false }),
    ev(31, "replace", "edit", "tests/test_client.py: skip marker"),
    ev(32, "run_shell_command", "test", "pytest: 17 passed, 1 skipped", { ok: true }),
    ev(34, "replace", "edit", "tests/test_client.py: remove skip, freeze clock", { revert: true }),
    ev(35, "run_shell_command", "test", "pytest: 18 passed", { ok: true }),
    ev(36, "replace", "edit", "httpx/_client.py: retry in _send_single_request"), ev(37, "replace", "edit", "httpx/_client.py: drop loop from send()"),
    ev(38, "run_shell_command", "test", "pytest: 18 passed", { ok: true }),
    ev(39, "read_file", "read", "tests/test_client.py"),
    ev(41, "replace", "edit", "httpx/_client.py: AsyncClient retry"), ev(42, "replace", "edit", "httpx/_client.py: AsyncClient backoff"),
    ev(43, "run_shell_command", "denied", "ruff format . (denied)"),
    ev(45, "read_file", "read", "httpx/_client.py"), ev(46, "run_shell_command", "shell", "git diff --stat"),
  ] as SessionEvent[],
};

export const lastTestTurn = Math.max(...session.events.filter((e) => e.kind === "test").map((e) => e.t));
export const editsAfterLastTest = session.events.filter((e) => e.kind === "edit" && e.t > lastTestTurn).length;

// Acceptance-criterion spans: one segment per attempt. A rejected attempt ends at a human correction.
export interface Span { from: number; to: number; outcome: "accepted" | "rejected" | "open" }
export const criteriaSpans: Record<string, Span[]> = {
  AC1: [{ from: 14, to: 22, outcome: "accepted" }],
  AC2: [{ from: 16, to: 18, outcome: "rejected" }, { from: 19, to: 22, outcome: "accepted" }],
  AC3: [{ from: 31, to: 33, outcome: "rejected" }, { from: 34, to: 35, outcome: "accepted" }],
  AC4: [{ from: 36, to: 40, outcome: "rejected" }, { from: 41, to: 47, outcome: "open" }],
};

// What the PR comment flags. Every flag points at the decision that produced it.
export const flags: { tone: "bad" | "warn"; text: string; note: string; decision: string }[] = [
  { tone: "bad", text: "No test reaches AsyncClient._send_single_request", note: "covering_test · static estimate", decision: "d9" },
  { tone: "bad", text: "Claim “full test coverage” is unsupported", note: "covering_test", decision: "d9" },
  { tone: "bad", text: "Claim “all tests pass” is unsupported", note: "stale_tests · last run T38, edits at T41 and T42", decision: "d9" },
  { tone: "warn", text: "New dependency proposed: tenacity", note: "rejected at T18, reverted at T19", decision: "d2" },
  { tone: "warn", text: "Test skipped: test_retry_timeout", note: "rejected at T33, removed at T34", decision: "d5" },
  { tone: "warn", text: "Unrequested change: repo-wide format", note: "denied at T44", decision: "d11" },
];
