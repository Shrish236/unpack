// Illustrative governance data, shaped like Policy / PolicyCandidate / OverrideEvent in docs/UNPACK_BRIEF.md §6.3.
import type { DType, HumanKind } from "./data";

export type Scope = "repo" | "team" | "org";
export type Enforcement = "advice" | "check" | "gate";

// "Today" for the mock, so expiry maths is stable.
export const TODAY = "2026-11-20";

export interface Evidence {
  id: string;
  session: string;
  pr: string;
  team: string;
  dev: string; // hashed id, never a name
  turn: number;
  kind: HumanKind;
  proposal: string; // what the agent proposed
  choice: string; // what the human chose
  quote: string; // the human's exact words
  when: string;
}

export interface Candidate {
  id: string;
  pid: string; // id the policy gets if approved
  statement: string;
  type: DType;
  sessions: number;
  teams: number;
  developers: number;
  trend: number[]; // overrides per week, oldest first
  perHundred: number; // overrides per 100 sessions today
  match: string; // what the PR check looks for
  scope: Scope;
  enforcement: Enforcement;
  owner: string;
  expires: string;
  evidence: Evidence[];
}

export interface ActivePolicy {
  id: string;
  statement: string;
  type: DType;
  scope: Scope;
  scopeName: string;
  enforcement: Enforcement;
  owner: string;
  expires: string;
  adherence: number | null; // null while it is still being measured
  before: number; // overrides per 100 sessions before the policy
  after: number | null;
  match: string;
  recurrence?: { sessions: number; teams: number; developers: number; evidence: Evidence[] };
}

export interface SkillRule {
  id: string;
  text: string;
  skill: string;
  followed: number;
  violated: number;
  trend: number[]; // violations per week
  latestPr: string;
  latestTurn: number;
}

export interface HistoryItem {
  id: string;
  statement: string;
  outcome: "approved" | "rejected" | "expired";
  role: string;
  when: string;
  why: string;
}

export const candidates: Candidate[] = [
  {
    id: "c1", pid: "P-12", type: "dependency", statement: "Add no new runtime dependency without approval.",
    sessions: 11, teams: 3, developers: 7, trend: [1, 1, 2, 1, 3, 2, 4, 3], perHundred: 11,
    match: "diff touches package.json, requirements.txt, pyproject.toml or go.mod",
    scope: "org", enforcement: "check", owner: "@platform", expires: "2027-03-01",
    evidence: [
      { id: "e1", session: "s-4f1a", pr: "#482", team: "Payments", dev: "dev-7f3a", turn: 18, kind: "redirect", when: "Nov 19",
        proposal: "Add tenacity to pyproject.toml", choice: "Write the backoff with the standard library",
        quote: "Don't add a library for this. Write the backoff with what we already have." },
      { id: "e2", session: "s-91c2", pr: "#470", team: "Identity", dev: "dev-2b8e", turn: 9, kind: "reject", when: "Nov 17",
        proposal: "pip install python-jose to parse JWTs", choice: "Use the existing token helper",
        quote: "No. We already have a JWT helper in auth/tokens.py, use that." },
      { id: "e3", session: "s-77d0", pr: "#455", team: "Search", dev: "dev-c41d", turn: 22, kind: "permission_denied", when: "Nov 12",
        proposal: "npm install lodash for a debounce", choice: "Denied the install",
        quote: "(permission denied for: npm install lodash)" },
      { id: "e4", session: "s-0a3e", pr: "#448", team: "Payments", dev: "dev-5e90", turn: 14, kind: "revert", when: "Nov 10",
        proposal: "Add httpx-retries to requirements.txt", choice: "Removed it, kept the local retry loop",
        quote: "Reverted the requirements.txt edit and kept our own retry loop." },
    ],
  },
  {
    id: "c2", pid: "P-13", type: "test", statement: "Never skip or delete a failing test. Find the cause.",
    sessions: 8, teams: 3, developers: 5, trend: [0, 1, 1, 2, 1, 2, 3, 2], perHundred: 8,
    match: "diff adds skip or xfail markers, or deletes a test that failed earlier in the session",
    scope: "org", enforcement: "gate", owner: "@quality", expires: "2027-03-01",
    evidence: [
      { id: "e5", session: "s-4f1a", pr: "#482", team: "Payments", dev: "dev-7f3a", turn: 33, kind: "reject", when: "Nov 19",
        proposal: "Mark test_retry_timeout as skipped", choice: "Keep the test and fix the mock clock",
        quote: "No skipping tests. Find out why it times out." },
      { id: "e6", session: "s-c05b", pr: "#466", team: "Identity", dev: "dev-91ad", turn: 27, kind: "redirect", when: "Nov 14",
        proposal: "Add @pytest.mark.skip to test_upload_race", choice: "Fix the race with a fake clock",
        quote: "Don't skip it, it's telling us something. Fake the clock." },
      { id: "e7", session: "s-2e19", pr: "#459", team: "Search", dev: "dev-c41d", turn: 41, kind: "revert", when: "Nov 11",
        proposal: "Delete test_refund_partial after two failures", choice: "Restore it and fix the fixture",
        quote: "Put that test back. The fixture is wrong, not the test." },
    ],
  },
  {
    id: "c3", pid: "P-14", type: "scope", statement: "Cover the async client whenever the sync client changes.",
    sessions: 3, teams: 2, developers: 2, trend: [0, 0, 0, 1, 0, 1, 1, 1], perHundred: 3,
    match: "diff changes a Client method with no matching change in AsyncClient",
    scope: "repo", enforcement: "advice", owner: "@platform", expires: "2027-02-01",
    evidence: [
      { id: "e8", session: "s-4f1a", pr: "#482", team: "Payments", dev: "dev-7f3a", turn: 40, kind: "requirement", when: "Nov 19",
        proposal: "Retry added to Client only", choice: "Add the same behaviour to AsyncClient",
        quote: "This has to work for AsyncClient as well, same behaviour." },
      { id: "e9", session: "s-5d77", pr: "#463", team: "Payments", dev: "dev-5e90", turn: 18, kind: "requirement", when: "Nov 13",
        proposal: "Timeout option added to Session", choice: "Mirror it on AsyncSession",
        quote: "Do the same for AsyncSession, they should not drift." },
      { id: "e10", session: "s-b812", pr: "#452", team: "Search", dev: "dev-c41d", turn: 30, kind: "discussion", when: "Nov 8",
        proposal: "Ship sync first, async later", choice: "Both in one PR",
        quote: "Let's do both now. A sync-only fix will be forgotten." },
    ],
  },
  {
    id: "c4", pid: "P-15", type: "architecture", statement: "Add HTTP behaviour in the transport layer, not in Client.send.",
    sessions: 4, teams: 2, developers: 2, trend: [0, 1, 0, 0, 1, 1, 1, 1], perHundred: 4,
    match: "diff adds retry, timeout or header logic inside Client.send or AsyncClient.send",
    scope: "team", enforcement: "advice", owner: "@platform", expires: "2027-02-15",
    evidence: [
      { id: "e11", session: "s-3a90", pr: "#471", team: "Payments", dev: "dev-5e90", turn: 12, kind: "discussion", when: "Nov 15",
        proposal: "Wrap Client.send in a loop", choice: "Put it in the transport",
        quote: "Option B. Transport is the layer that knows about connections." },
      { id: "e12", session: "s-9e04", pr: "#460", team: "Search", dev: "dev-c41d", turn: 25, kind: "redirect", when: "Nov 11",
        proposal: "Add header injection in Client.send", choice: "Move it to a transport wrapper",
        quote: "Not in send(). Wrap the transport instead." },
    ],
  },
  {
    id: "c5", pid: "P-16", type: "design", statement: "Don't rename public functions in the same PR as a behaviour change.",
    sessions: 2, teams: 1, developers: 1, trend: [0, 0, 0, 0, 1, 0, 0, 1], perHundred: 2,
    match: "diff renames a public function and changes its logic hash",
    scope: "repo", enforcement: "advice", owner: "@api-guild", expires: "2027-02-01",
    evidence: [
      { id: "e13", session: "s-6c21", pr: "#468", team: "Identity", dev: "dev-91ad", turn: 15, kind: "reject", when: "Nov 14",
        proposal: "Rename verify() to validate() while fixing it", choice: "Fix first, rename in a separate PR",
        quote: "One thing at a time. Fix it, rename later." },
      { id: "e14", session: "s-d0f3", pr: "#457", team: "Identity", dev: "dev-91ad", turn: 8, kind: "redirect", when: "Nov 9",
        proposal: "Rename get_user to fetch_user alongside a caching change", choice: "Keep the name for now",
        quote: "Keep the name. I'll rename it after this lands." },
    ],
  },
];

export const actives: ActivePolicy[] = [
  { id: "P-09", statement: "Retries: exponential backoff, at most 5 attempts.", type: "retries", scope: "team", scopeName: "Payments",
    enforcement: "check", owner: "@platform", expires: "2027-02-14", adherence: 92, before: 9, after: 2,
    match: "diff adds a retry loop without a backoff or with more than 5 attempts" },
  { id: "P-07", statement: "Never skip or delete a failing test without a linked issue.", type: "test", scope: "org", scopeName: "Org",
    enforcement: "gate", owner: "@quality", expires: "2027-06-30", adherence: 71, before: 14, after: 9,
    match: "diff adds skip or xfail markers",
    recurrence: { sessions: 9, teams: 3, developers: 6, evidence: [
      { id: "e20", session: "s-e4a1", pr: "#474", team: "Identity", dev: "dev-91ad", turn: 29, kind: "reject", when: "Nov 18",
        proposal: "Skip test_token_expiry, linked issue is 'later'", choice: "Fix it now",
        quote: "A placeholder issue isn't a reason. Fix the test." },
    ] } },
  { id: "P-05", statement: "Public API changes need a changelog entry.", type: "design", scope: "repo", scopeName: "api",
    enforcement: "advice", owner: "@api-guild", expires: "2026-12-18", adherence: 88, before: 6, after: 3,
    match: "diff changes a public signature with no CHANGELOG.md edit" },
  { id: "P-04", statement: "Use the repo's HTTP client. No new HTTP libraries.", type: "dependency", scope: "repo", scopeName: "payments-service",
    enforcement: "gate", owner: "@platform", expires: "2027-05-01", adherence: 96, before: 7, after: 1,
    match: "diff imports requests, urllib3 or aiohttp in application code" },
];

export const rules: SkillRule[] = [
  { id: "r1", text: "Claims must be backed by a test that reaches the code", skill: "skills/claims.md", followed: 30, violated: 12, trend: [1, 2, 1, 3, 2, 1, 2, 2], latestPr: "#482", latestTurn: 47 },
  { id: "r2", text: "Never skip or delete a failing test", skill: "skills/tests.md", followed: 63, violated: 9, trend: [2, 1, 2, 1, 1, 0, 1, 1], latestPr: "#482", latestTurn: 31 },
  { id: "r3", text: "No new runtime dependency without approval", skill: "skills/dependencies.md", followed: 41, violated: 7, trend: [0, 1, 1, 1, 0, 2, 1, 1], latestPr: "#482", latestTurn: 16 },
  { id: "r4", text: "Public API changes need a changelog entry", skill: "skills/api.md", followed: 54, violated: 6, trend: [1, 0, 1, 1, 1, 0, 1, 1], latestPr: "#474", latestTurn: 22 },
  { id: "r5", text: "Retry at the lowest transport layer", skill: "skills/retries.md", followed: 18, violated: 2, trend: [0, 0, 1, 0, 0, 0, 1, 0], latestPr: "#471", latestTurn: 12 },
  { id: "r6", text: "Retries: exponential backoff, at most 5 attempts", skill: "skills/retries.md", followed: 22, violated: 1, trend: [0, 0, 0, 1, 0, 0, 0, 0], latestPr: "#455", latestTurn: 34 },
];

export const history: HistoryItem[] = [
  { id: "h1", statement: "Retries: exponential backoff, at most 5 attempts.", outcome: "approved", role: "Tech lead, Payments", when: "2026-10-14", why: "9 sessions across 3 teams. Matches existing platform guidance." },
  { id: "h2", statement: "Always add type hints to new functions.", outcome: "rejected", role: "Platform reviewer", when: "2026-10-09", why: "One team's style preference. The linter already covers it." },
  { id: "h3", statement: "Freeze dependency versions during release week.", outcome: "expired", role: "Release manager", when: "2026-09-30", why: "Expired after the Q3 release and was not renewed." },
  { id: "h4", statement: "Public API changes need a changelog entry.", outcome: "approved", role: "API guild lead", when: "2026-09-12", why: "6 sessions across 2 teams. Reviewers kept asking for it by hand." },
  { id: "h5", statement: "Prefer dataclasses over plain dicts.", outcome: "rejected", role: "Tech lead, Identity", when: "2026-09-03", why: "Two developers on one team. Revisit if it spreads." },
  { id: "h6", statement: "Use the repo's HTTP client. No new HTTP libraries.", outcome: "approved", role: "Tech lead, Payments", when: "2026-08-21", why: "7 sessions across 3 teams. First policy to reach a hard gate." },
];
