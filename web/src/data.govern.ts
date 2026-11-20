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
  target?: number; // overrides per 100 sessions the policy is meant to reach
  review?: string; // date the owner checks whether it worked
  approved?: string;
  weekly?: number[]; // overrides per 100 sessions, per week since approval, oldest first
  checks?: { flagged: number; wrong: number }; // PRs the check flagged, and how many a reviewer overrode as wrong
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
  outcome: "approved" | "rejected" | "expired" | "watching";
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
    enforcement: "check", owner: "@platform", expires: "2027-02-14", adherence: 92, before: 9, after: 2, target: 2, approved: "2026-10-14", weekly: [9, 7, 5, 4, 3, 2, 2, 2], checks: { flagged: 14, wrong: 1 },
    match: "diff adds a retry loop without a backoff or with more than 5 attempts" },
  { id: "P-07", statement: "Never skip or delete a failing test without a linked issue.", type: "test", scope: "org", scopeName: "Org",
    enforcement: "gate", owner: "@quality", expires: "2027-06-30", adherence: 71, before: 14, after: 9, target: 5, approved: "2026-08-05", weekly: [14, 13, 12, 11, 10, 10, 9, 9], checks: { flagged: 31, wrong: 9 },
    match: "diff adds skip or xfail markers",
    recurrence: { sessions: 9, teams: 3, developers: 6, evidence: [
      { id: "e20", session: "s-e4a1", pr: "#474", team: "Identity", dev: "dev-91ad", turn: 29, kind: "reject", when: "Nov 18",
        proposal: "Skip test_token_expiry, linked issue is 'later'", choice: "Fix it now",
        quote: "A placeholder issue isn't a reason. Fix the test." },
    ] } },
  { id: "P-05", statement: "Public API changes need a changelog entry.", type: "design", scope: "repo", scopeName: "api",
    enforcement: "advice", owner: "@api-guild", expires: "2026-12-18", adherence: 88, before: 6, after: 3, target: 2, approved: "2026-09-12", weekly: [6, 5, 4, 4, 3, 3, 3, 3],
    match: "diff changes a public signature with no CHANGELOG.md edit" },
  { id: "P-04", statement: "Use the repo's HTTP client. No new HTTP libraries.", type: "dependency", scope: "repo", scopeName: "payments-service",
    enforcement: "gate", owner: "@platform", expires: "2027-05-01", adherence: 96, before: 7, after: 1, target: 1, approved: "2026-08-21", weekly: [7, 4, 3, 2, 1, 1, 1, 1], checks: { flagged: 12, wrong: 0 },
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

// ---- Decision brief ----------------------------------------------------------------------------
// What a reviewer needs to decide on a candidate, beyond the quotes. Illustrative; shaped so a server
// endpoint can return it later. Window: last 8 weeks for sessions, last 90 days for the PR replay.

export interface TeamSplit { team: string; developers: number; overruled: number; accepted: number } // accepted = same proposal, nobody objected
export interface Reach { repos: number; teams: number; scanned: number; flagged: number; confirmed: number } // PR replay over 90 days
export interface Conflict { id: string; level: "overlap" | "conflict"; note: string }
export interface Recommendation { action: "approve" | "trial" | "wait"; enforcement: Enforcement; reason: string }
export interface Brief {
  proposed: number; // sessions in which the agent made this kind of proposal
  teams: TeamSplit[];
  areas: { area: string; n: number }[];
  rework: { turns: number; hours: number; prs: number }; // work undone or redone after the override
  reach: Record<Scope, Reach>;
  conflicts: Conflict[];
  recommend: Recommendation;
}

export const briefs: Record<string, Brief> = {
  // Reopened from P-07 with "Revise": why the existing wording keeps being overridden.
  "c-P-07": {
    proposed: 14,
    teams: [
      { team: "Payments", developers: 2, overruled: 3, accepted: 1 },
      { team: "Identity", developers: 2, overruled: 3, accepted: 2 },
      { team: "Search", developers: 2, overruled: 3, accepted: 2 },
    ],
    areas: [{ area: "tests/ with a placeholder issue link", n: 6 }, { area: "tests/fixtures", n: 3 }],
    rework: { turns: 33, hours: 2.7, prs: 5 },
    reach: {
      repo: { repos: 1, teams: 1, scanned: 31, flagged: 4, confirmed: 4 },
      team: { repos: 4, teams: 1, scanned: 52, flagged: 6, confirmed: 5 },
      org: { repos: 14, teams: 6, scanned: 168, flagged: 17, confirmed: 15 },
    },
    conflicts: [{ id: "P-07", level: "overlap", note: "This replaces P-07. The current wording lets a placeholder issue link satisfy it, which is why it keeps being overridden. Approving retires P-07." }],
    recommend: { action: "approve", enforcement: "gate", reason: "The tightened wording would have been right 88% of the time. The only failures of P-07 are the placeholder-issue loophole." },
  },
  c1: {
    proposed: 19,
    teams: [
      { team: "Payments", developers: 3, overruled: 5, accepted: 1 },
      { team: "Identity", developers: 2, overruled: 3, accepted: 3 },
      { team: "Search", developers: 2, overruled: 3, accepted: 4 },
    ],
    areas: [{ area: "pyproject.toml / requirements.txt", n: 6 }, { area: "package.json", n: 3 }, { area: "go.mod", n: 2 }],
    rework: { turns: 41, hours: 3.1, prs: 6 },
    reach: {
      repo: { repos: 1, teams: 1, scanned: 31, flagged: 6, confirmed: 6 },
      team: { repos: 4, teams: 1, scanned: 52, flagged: 9, confirmed: 8 },
      org: { repos: 14, teams: 6, scanned: 168, flagged: 21, confirmed: 18 },
    },
    conflicts: [{ id: "P-04", level: "overlap", note: "P-04 already blocks new HTTP libraries in payments-service. This rule generalises it to every dependency and every repo." }],
    recommend: { action: "approve", enforcement: "check", reason: "Overruled in most sessions across all three teams, and the check would have been right 86% of the time. A hard gate would have blocked 3 PRs wrongly." },
  },
  c2: {
    proposed: 14,
    teams: [
      { team: "Payments", developers: 2, overruled: 3, accepted: 1 },
      { team: "Identity", developers: 2, overruled: 3, accepted: 2 },
      { team: "Search", developers: 1, overruled: 2, accepted: 3 },
    ],
    areas: [{ area: "tests/ (skip or xfail markers)", n: 5 }, { area: "tests/fixtures", n: 3 }],
    rework: { turns: 29, hours: 2.4, prs: 4 },
    reach: {
      repo: { repos: 1, teams: 1, scanned: 31, flagged: 3, confirmed: 3 },
      team: { repos: 4, teams: 1, scanned: 52, flagged: 4, confirmed: 4 },
      org: { repos: 14, teams: 6, scanned: 168, flagged: 12, confirmed: 11 },
    },
    conflicts: [{ id: "P-07", level: "conflict", note: "P-07 already gates skipping a test without a linked issue, and 9 sessions overrode it because a placeholder issue satisfies it. This rule is stricter. Approving it should replace P-07, not sit beside it." }],
    recommend: { action: "approve", enforcement: "gate", reason: "The check would have been right 92% of the time, and the existing gate (P-07) is being worked around. Replacing it closes the loophole." },
  },
  c3: {
    proposed: 12,
    teams: [
      { team: "Payments", developers: 2, overruled: 2, accepted: 3 },
      { team: "Search", developers: 1, overruled: 1, accepted: 6 },
    ],
    areas: [{ area: "Client / AsyncClient", n: 2 }, { area: "Session / AsyncSession", n: 1 }],
    rework: { turns: 9, hours: 0.7, prs: 2 },
    reach: {
      repo: { repos: 1, teams: 1, scanned: 31, flagged: 5, confirmed: 3 },
      team: { repos: 4, teams: 1, scanned: 52, flagged: 8, confirmed: 5 },
      org: { repos: 14, teams: 6, scanned: 168, flagged: 15, confirmed: 9 },
    },
    conflicts: [],
    recommend: { action: "trial", enforcement: "advice", reason: "Only a quarter of proposals were overruled and the match is wrong 4 times in 10, so a check would be noisy. Start as advice and see whether overrides fall." },
  },
  c4: {
    proposed: 9,
    teams: [
      { team: "Payments", developers: 1, overruled: 2, accepted: 2 },
      { team: "Search", developers: 1, overruled: 2, accepted: 3 },
    ],
    areas: [{ area: "Client.send / AsyncClient.send", n: 3 }, { area: "transport/", n: 1 }],
    rework: { turns: 14, hours: 1.1, prs: 3 },
    reach: {
      repo: { repos: 1, teams: 1, scanned: 31, flagged: 3, confirmed: 3 },
      team: { repos: 4, teams: 1, scanned: 52, flagged: 4, confirmed: 3 },
      org: { repos: 14, teams: 6, scanned: 168, flagged: 7, confirmed: 6 },
    },
    conflicts: [{ id: "r5", level: "overlap", note: "The skill rule \"Retry at the lowest transport layer\" covers retries only. This rule extends the same idea to timeouts and headers." }],
    recommend: { action: "trial", enforcement: "advice", reason: "Placement is a judgement call, so a mechanical check will miss cases. Two developers agree. Publish as advice and review in 30 days." },
  },
  c5: {
    proposed: 6,
    teams: [{ team: "Identity", developers: 1, overruled: 2, accepted: 4 }],
    areas: [{ area: "auth/ (renames)", n: 2 }],
    rework: { turns: 4, hours: 0.3, prs: 1 },
    reach: {
      repo: { repos: 1, teams: 1, scanned: 31, flagged: 5, confirmed: 3 },
      team: { repos: 4, teams: 1, scanned: 52, flagged: 5, confirmed: 3 },
      org: { repos: 14, teams: 6, scanned: 168, flagged: 5, confirmed: 3 },
    },
    conflicts: [],
    recommend: { action: "wait", enforcement: "advice", reason: "One developer on one team. This is a preference until a second developer makes the same correction." },
  },
};
