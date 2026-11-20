"""Dummy data for the dashboard pages: executive, managers and governance.

Run with `make seed-dashboard`. It empties every dashboard table and loads the rows again, so running it
twice gives the same result. The numbers are illustrative and copied from the design mock. Nothing here is
measured from sessions yet. Dates are anchored on ANCHOR so the story reads the same as the mock.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .db import session_scope
from .models import (
    DASHBOARD_TABLES,
    ConsistencyItem,
    ConsistencyRow,
    ExecAgent,
    ExecHumanKind,
    ExecPeriod,
    ExecPolicyEvent,
    ExecWeek,
    GovCandidate,
    GovEvidence,
    GovHistory,
    GovPolicy,
    GovSkillRule,
    Team,
    TeamArea,
    TeamAreaWeek,
    TeamMix,
    TeamPR,
    TeamSuggestion,
    TeamTool,
)

# The mock's "today". Every seeded date is relative to it.
ANCHOR = date(2026, 11, 20)
EXEC_START = date(2026, 8, 31)  # Monday. Twelve weeks, the last one starts 16 Nov
TEAM_START = date(2026, 9, 28)  # Monday. Eight weeks, the last one starts 16 Nov

TYPES = ["architecture", "design", "dependency", "retries", "test", "scope"]


def _d(value: str) -> date:
    return date.fromisoformat(value)


# ----------------------------------------------------------------------------- executive

EXEC_ADHERENCE = [71, 72, 70, 74, 75, 77, 78, 81, 83, 84, 85, 86]
EXEC_REPEAT = [12, 13, 12, 11, 12, 11, 11, 8, 6, 5, 4, 3]
EXEC_HUMAN_PER_WEEK = [26, 28, 27, 28, 27, 29, 29, 27, 25, 25, 24, 25]
EXEC_MIX = {
    "architecture": [18, 20, 19, 22, 21, 23, 22, 24, 23, 25, 24, 26],
    "design": [14, 15, 15, 16, 17, 16, 18, 17, 18, 19, 18, 20],
    "dependency": [20, 22, 21, 19, 20, 19, 18, 12, 9, 7, 6, 5],
    "retries": [9, 10, 10, 11, 10, 12, 11, 12, 13, 12, 14, 13],
    "test": [24, 26, 25, 27, 28, 27, 29, 28, 30, 31, 30, 32],
    "scope": [8, 9, 8, 10, 9, 11, 10, 12, 11, 13, 12, 14],
}

EXEC_PERIODS = [
    # period, adherence, adherence_delta, override, override_before, verified, verified_delta,
    # unrequested, unrequested_delta, pending, pending_oldest_days, sessions, first, missed, thin
    ("30d", 86, 5, 3.0, 11.0, 78, 4, 9, -2, 3, 4, 912, 71, 38, 31),
    ("90d", 81, 11, 5.6, 11.8, 74, 9, 11, -5, 3, 4, 2640, 214, 131, 97),
]

EXEC_HUMAN_KINDS = [
    ("redirect", "Redirected the agent", 36),
    ("reject", "Rejected a proposal", 28),
    ("requirement", "Added a requirement", 22),
    ("discussion", "Chose in discussion", 9),
    ("permission_denied", "Denied a tool call", 5),
]

EXEC_AGENTS = [
    ("gemini-3.1-pro-preview", "Gemini CLI", 1214, 84, 6, 1.5, "advice"),
    ("gemini-2.5-pro", "Gemini CLI", 782, 79, 9, 1.7, "check"),
    ("gemini-3.5-flash", "Gemini CLI", 436, 63, 17, 2.1, "gate"),
    ("Claude Code", "adapter on the roadmap", None, None, None, None, None),
]

# week_index is the position in the twelve-week series. headline marks the policy the page reports on.
EXEC_POLICY_EVENTS = [
    ("P-09", 3, "Retries: exponential backoff, at most 5 attempts", False),
    ("P-12", 7, "No new runtime dependency without approval", True),
    ("P-14", 10, "Claims must be backed by a test that reaches the code", False),
]

# ----------------------------------------------------------------------------- teams

TEAMS = [
    {
        "id": "payments", "name": "Payments",
        "pr_count": 38, "prs_delta": "+6", "attempts": 1.71, "attempts_delta": "+0.18", "overrules": 1.4,
        "thin": 19, "unsupported": 11, "funnel": (112, 61, 29, 22, 9, 5),
        "areas": [
            ("payments/client", [1.3, 1.4, 1.2, 1.6, 2.1, 2.4, 2.2, 1.9], [1, 1, 0, 2, 4, 5, 4, 3]),
            ("payments/ledger", [1.1, 1.0, 1.2, 1.1, 1.3, 1.2, 1.1, 1.2], [0, 0, 1, 0, 1, 1, 0, 1]),
            ("payments/webhooks", [0, 1.5, 1.8, 1.4, 0, 1.6, 1.7, 2.0], [0, 2, 3, 1, 0, 2, 2, 4]),
            ("payments/refunds", [1.2, 0, 1.3, 1.5, 1.4, 0, 1.2, 1.3], [1, 0, 1, 2, 1, 0, 1, 1]),
            ("shared/http", [0, 0, 1.1, 0, 1.9, 2.2, 0, 1.4], [0, 0, 0, 0, 3, 4, 0, 2]),
        ],
        "suggestions": [
            ("requirement-thin", "Add a parity line to the ticket template: “applies to Client and AsyncClient”.", [482, 471, 455]),
            ("agent-missed", "Agents add a new package for small helpers. The skill rule exists but is not applied in payments/client.", [482, 468]),
            ("requirement-thin", "Webhook tickets omit the retry budget. Humans add it at the second turn.", [477, 463]),
        ],
        "mix": [("architecture", 31, 6), ("design", 27, 9), ("dependency", 14, 11), ("retries", 18, 7), ("test", 33, 12), ("scope", 6, 15)],
        "tools": [("read_file", 1480, 1_310_000), ("replace", 610, 1_790_000), ("run_shell_command", 430, 320_000),
                  ("grep_search", 340, 150_000), ("write_todos", 96, 41_000), ("write_file", 74, 108_000)],
        "prs": [
            (482, "Add retry to the payments client", "payments/client", 7, "Gemini CLI", 6, 3, 2, 1.75, ["unsupported", "new-dependency", "skipped-test"]),
            (477, "Retry failed webhook deliveries", "payments/webhooks", 7, "Gemini CLI", 8, 4, 2, 2.0, ["async-gap"]),
            (471, "Idempotency keys for refunds", "payments/refunds", 6, "Claude Code", 7, 2, 1, 1.3, []),
            (468, "Shared HTTP client timeouts", "shared/http", 6, "Gemini CLI", 5, 5, 4, 2.2, ["new-dependency"]),
            (463, "Webhook signature rotation", "payments/webhooks", 5, "Claude Code", 9, 3, 2, 1.6, []),
            (455, "Ledger entry reconciliation", "payments/ledger", 4, "Gemini CLI", 6, 1, 0, 1.1, []),
            (449, "Async client connection pool", "payments/client", 4, "Gemini CLI", 7, 4, 3, 2.1, ["unsupported", "skipped-test"]),
        ],
    },
    {
        "id": "auth", "name": "Auth",
        "pr_count": 24, "prs_delta": "+2", "attempts": 1.42, "attempts_delta": "−0.05", "overrules": 0.9,
        "thin": 12, "unsupported": 6, "funnel": (71, 46, 13, 7, 3, 2),
        "areas": [
            ("auth/session", [1.2, 1.1, 1.3, 1.2, 1.4, 1.2, 1.1, 1.3], [0, 0, 1, 1, 1, 0, 0, 1]),
            ("auth/oauth", [0, 1.6, 1.9, 1.7, 1.5, 0, 1.4, 1.6], [0, 2, 3, 2, 1, 0, 1, 2]),
            ("auth/tokens", [1.1, 0, 1.2, 1.0, 0, 1.3, 1.2, 0], [0, 0, 1, 0, 0, 1, 1, 0]),
            ("auth/admin", [0, 0, 0, 1.5, 1.3, 0, 1.2, 1.1], [0, 0, 0, 1, 1, 0, 0, 0]),
        ],
        "suggestions": [
            ("agent-missed", "Agents read token lifetimes from env instead of the config module.", [479, 466]),
            ("requirement-thin", "OAuth tickets leave out the error redirect behaviour.", [473]),
        ],
        "mix": [("architecture", 12, 3), ("design", 15, 4), ("dependency", 6, 4), ("retries", 3, 1), ("test", 19, 5), ("scope", 3, 8)],
        "tools": [("read_file", 910, 790_000), ("replace", 320, 940_000), ("run_shell_command", 260, 190_000),
                  ("grep_search", 210, 88_000), ("write_todos", 48, 20_000), ("write_file", 41, 61_000)],
        "prs": [
            (479, "Rotate refresh tokens on use", "auth/tokens", 7, "Claude Code", 6, 2, 1, 1.3, []),
            (473, "OAuth error redirects", "auth/oauth", 6, "Gemini CLI", 7, 3, 2, 1.9, ["unsupported"]),
            (466, "Session expiry sliding window", "auth/session", 5, "Gemini CLI", 5, 2, 1, 1.4, []),
            (458, "Admin impersonation audit log", "auth/admin", 4, "Claude Code", 8, 1, 0, 1.1, []),
            (452, "PKCE for mobile clients", "auth/oauth", 3, "Gemini CLI", 6, 3, 2, 1.7, ["new-dependency"]),
        ],
    },
    {
        "id": "search", "name": "Search",
        "pr_count": 17, "prs_delta": "−1", "attempts": 1.93, "attempts_delta": "+0.31", "overrules": 2.1,
        "thin": 28, "unsupported": 16, "funnel": (48, 19, 11, 12, 3, 3),
        "areas": [
            ("search/index", [1.4, 1.6, 1.5, 1.9, 2.2, 2.5, 2.3, 2.6], [1, 2, 2, 3, 4, 5, 5, 6]),
            ("search/query", [1.2, 1.3, 0, 1.5, 1.4, 1.6, 0, 1.5], [0, 1, 0, 2, 1, 2, 0, 2]),
            ("search/ranking", [0, 0, 1.8, 2.0, 0, 1.7, 1.9, 0], [0, 0, 3, 3, 0, 2, 3, 0]),
        ],
        "suggestions": [
            ("requirement-thin", "Index tickets do not state the reindex strategy. The agent picks one, a human changes it.", [480, 474, 465]),
            ("agent-missed", "Agents quarantine flaky tests with a marker instead of fixing the cause.", [474]),
            ("requirement-thin", "Ranking changes lack a baseline query set in the brief.", [469]),
        ],
        "mix": [("architecture", 9, 5), ("design", 11, 6), ("dependency", 5, 3), ("retries", 2, 0), ("test", 13, 7), ("scope", 2, 9)],
        "tools": [("read_file", 620, 560_000), ("replace", 240, 700_000), ("run_shell_command", 190, 140_000),
                  ("grep_search", 170, 72_000), ("write_todos", 31, 13_000), ("write_file", 22, 33_000)],
        "prs": [
            (480, "Reindex on schema change", "search/index", 7, "Gemini CLI", 6, 4, 3, 2.6, ["unsupported", "skipped-test"]),
            (474, "Quarantine flaky query tests", "search/query", 5, "Gemini CLI", 5, 3, 2, 1.6, ["skipped-test"]),
            (469, "Boost exact title matches", "search/ranking", 6, "Claude Code", 7, 3, 3, 1.9, ["async-gap"]),
            (465, "Incremental index shards", "search/index", 5, "Gemini CLI", 8, 5, 5, 2.5, ["new-dependency", "unsupported"]),
        ],
    },
]

CONSISTENCY = [
    ("retries", "retries", "How do we retry a failed outbound call?", [
        ("payments", "Exponential, 5 tries, in the client layer", 9),
        ("auth", "Fixed 3 tries, in the caller", 4),
        ("search", "No retry, surface the error", 3),
    ]),
    ("timeouts", "design", "What is the default request timeout?", [
        ("payments", "10 s, set on the shared client", 6),
        ("auth", "30 s, set per call", 5),
        ("search", "5 s, set per call", 4),
    ]),
    ("flaky", "test", "What happens to a flaky test?", [
        ("payments", "Fix the cause. A human rejects any skip", 5),
        ("auth", "Fix the cause", 2),
        ("search", "Quarantine with a marker, fix later", 6),
    ]),
]

# ----------------------------------------------------------------------------- governance

# Candidates: an override that repeats. first_seen sets "waiting days" on the executive backlog.
CANDIDATES = [
    {
        "id": "c1", "pid": "P-12", "type": "dependency", "statement": "Add no new runtime dependency without approval.",
        "sessions": 11, "teams": 3, "developers": 7, "trend": [1, 1, 2, 1, 3, 2, 4, 3], "per_hundred": 11,
        "match": "diff touches package.json, requirements.txt, pyproject.toml or go.mod",
        "scope": "org", "enforcement": "check", "owner": "@platform", "expires": "2027-03-01", "first_seen": 4,
        "evidence": [
            ("e1", "s-4f1a", "#482", "Payments", "dev-7f3a", 18, "redirect", "2026-11-19", "Add tenacity to pyproject.toml", "Write the backoff with the standard library", "Don't add a library for this. Write the backoff with what we already have."),
            ("e2", "s-91c2", "#470", "Identity", "dev-2b8e", 9, "reject", "2026-11-17", "pip install python-jose to parse JWTs", "Use the existing token helper", "No. We already have a JWT helper in auth/tokens.py, use that."),
            ("e3", "s-77d0", "#455", "Search", "dev-c41d", 22, "permission_denied", "2026-11-12", "npm install lodash for a debounce", "Denied the install", "(permission denied for: npm install lodash)"),
            ("e4", "s-0a3e", "#448", "Payments", "dev-5e90", 14, "revert", "2026-11-10", "Add httpx-retries to requirements.txt", "Removed it, kept the local retry loop", "Reverted the requirements.txt edit and kept our own retry loop."),
        ],
    },
    {
        "id": "c2", "pid": "P-13", "type": "test", "statement": "Never skip or delete a failing test. Find the cause.",
        "sessions": 8, "teams": 3, "developers": 5, "trend": [0, 1, 1, 2, 1, 2, 3, 2], "per_hundred": 8,
        "match": "diff adds skip or xfail markers, or deletes a test that failed earlier in the session",
        "scope": "org", "enforcement": "gate", "owner": "@quality", "expires": "2027-03-01", "first_seen": 2,
        "evidence": [
            ("e5", "s-4f1a", "#482", "Payments", "dev-7f3a", 33, "reject", "2026-11-19", "Mark test_retry_timeout as skipped", "Keep the test and fix the mock clock", "No skipping tests. Find out why it times out."),
            ("e6", "s-c05b", "#466", "Identity", "dev-91ad", 27, "redirect", "2026-11-14", "Add @pytest.mark.skip to test_upload_race", "Fix the race with a fake clock", "Don't skip it, it's telling us something. Fake the clock."),
            ("e7", "s-2e19", "#459", "Search", "dev-c41d", 41, "revert", "2026-11-11", "Delete test_refund_partial after two failures", "Restore it and fix the fixture", "Put that test back. The fixture is wrong, not the test."),
        ],
    },
    {
        "id": "c3", "pid": "P-14", "type": "scope", "statement": "Cover the async client whenever the sync client changes.",
        "sessions": 3, "teams": 2, "developers": 2, "trend": [0, 0, 0, 1, 0, 1, 1, 1], "per_hundred": 3,
        "match": "diff changes a Client method with no matching change in AsyncClient",
        "scope": "repo", "enforcement": "advice", "owner": "@platform", "expires": "2027-02-01", "first_seen": 1,
        "evidence": [
            ("e8", "s-4f1a", "#482", "Payments", "dev-7f3a", 40, "requirement", "2026-11-19", "Retry added to Client only", "Add the same behaviour to AsyncClient", "This has to work for AsyncClient as well, same behaviour."),
            ("e9", "s-5d77", "#463", "Payments", "dev-5e90", 18, "requirement", "2026-11-13", "Timeout option added to Session", "Mirror it on AsyncSession", "Do the same for AsyncSession, they should not drift."),
            ("e10", "s-b812", "#452", "Search", "dev-c41d", 30, "discussion", "2026-11-08", "Ship sync first, async later", "Both in one PR", "Let's do both now. A sync-only fix will be forgotten."),
        ],
    },
    {
        "id": "c4", "pid": "P-15", "type": "architecture", "statement": "Add HTTP behaviour in the transport layer, not in Client.send.",
        "sessions": 4, "teams": 2, "developers": 2, "trend": [0, 1, 0, 0, 1, 1, 1, 1], "per_hundred": 4,
        "match": "diff adds retry, timeout or header logic inside Client.send or AsyncClient.send",
        "scope": "team", "enforcement": "advice", "owner": "@platform", "expires": "2027-02-15", "first_seen": 6,
        "evidence": [
            ("e11", "s-3a90", "#471", "Payments", "dev-5e90", 12, "discussion", "2026-11-15", "Wrap Client.send in a loop", "Put it in the transport", "Option B. Transport is the layer that knows about connections."),
            ("e12", "s-9e04", "#460", "Search", "dev-c41d", 25, "redirect", "2026-11-11", "Add header injection in Client.send", "Move it to a transport wrapper", "Not in send(). Wrap the transport instead."),
        ],
    },
    {
        "id": "c5", "pid": "P-16", "type": "design", "statement": "Don't rename public functions in the same PR as a behaviour change.",
        "sessions": 2, "teams": 1, "developers": 1, "trend": [0, 0, 0, 0, 1, 0, 0, 1], "per_hundred": 2,
        "match": "diff renames a public function and changes its logic hash",
        "scope": "repo", "enforcement": "advice", "owner": "@api-guild", "expires": "2027-02-01", "first_seen": 3,
        "evidence": [
            ("e13", "s-6c21", "#468", "Identity", "dev-91ad", 15, "reject", "2026-11-14", "Rename verify() to validate() while fixing it", "Fix first, rename in a separate PR", "One thing at a time. Fix it, rename later."),
            ("e14", "s-d0f3", "#457", "Identity", "dev-91ad", 8, "redirect", "2026-11-09", "Rename get_user to fetch_user alongside a caching change", "Keep the name for now", "Keep the name. I'll rename it after this lands."),
        ],
    },
]

POLICIES = [
    {
        "id": "P-09", "statement": "Retries: exponential backoff, at most 5 attempts.", "type": "retries",
        "scope": "team", "scope_name": "Payments", "enforcement": "check", "owner": "@platform", "expires": "2027-02-14",
        "adherence": 92, "before": 9, "after": 2, "match": "diff adds a retry loop without a backoff or with more than 5 attempts",
        "recurrence": None, "published_on": "2026-10-14",
    },
    {
        "id": "P-07", "statement": "Never skip or delete a failing test without a linked issue.", "type": "test",
        "scope": "org", "scope_name": "Org", "enforcement": "gate", "owner": "@quality", "expires": "2027-06-30",
        "adherence": 71, "before": 14, "after": 9, "match": "diff adds skip or xfail markers",
        "recurrence": (9, 3, 6),
        "evidence": [
            ("e20", "s-e4a1", "#474", "Identity", "dev-91ad", 29, "reject", "2026-11-18", "Skip test_token_expiry, linked issue is 'later'", "Fix it now", "A placeholder issue isn't a reason. Fix the test."),
        ],
        "published_on": "2026-09-03",
    },
    {
        "id": "P-05", "statement": "Public API changes need a changelog entry.", "type": "design",
        "scope": "repo", "scope_name": "api", "enforcement": "advice", "owner": "@api-guild", "expires": "2026-12-18",
        "adherence": 88, "before": 6, "after": 3, "match": "diff changes a public signature with no CHANGELOG.md edit",
        "recurrence": None, "published_on": "2026-09-12",
    },
    {
        "id": "P-04", "statement": "Use the repo's HTTP client. No new HTTP libraries.", "type": "dependency",
        "scope": "repo", "scope_name": "payments-service", "enforcement": "gate", "owner": "@platform", "expires": "2027-05-01",
        "adherence": 96, "before": 7, "after": 1, "match": "diff imports requests, urllib3 or aiohttp in application code",
        "recurrence": None, "published_on": "2026-08-21",
    },
]

SKILL_RULES = [
    ("r1", "Claims must be backed by a test that reaches the code", "skills/claims.md", 30, 12, [1, 2, 1, 3, 2, 1, 2, 2], "#482", 47),
    ("r2", "Never skip or delete a failing test", "skills/tests.md", 63, 9, [2, 1, 2, 1, 1, 0, 1, 1], "#482", 31),
    ("r3", "No new runtime dependency without approval", "skills/dependencies.md", 41, 7, [0, 1, 1, 1, 0, 2, 1, 1], "#482", 16),
    ("r4", "Public API changes need a changelog entry", "skills/api.md", 54, 6, [1, 0, 1, 1, 1, 0, 1, 1], "#474", 22),
    ("r5", "Retry at the lowest transport layer", "skills/retries.md", 18, 2, [0, 0, 1, 0, 0, 0, 1, 0], "#471", 12),
    ("r6", "Retries: exponential backoff, at most 5 attempts", "skills/retries.md", 22, 1, [0, 0, 0, 1, 0, 0, 0, 0], "#455", 34),
]

# Newest first, as the list shows it. Inserted oldest first so seq orders it.
HISTORY = [
    ("h1", "Retries: exponential backoff, at most 5 attempts.", "approved", "Tech lead, Payments", "2026-10-14", "9 sessions across 3 teams. Matches existing platform guidance."),
    ("h2", "Always add type hints to new functions.", "rejected", "Platform reviewer", "2026-10-09", "One team's style preference. The linter already covers it."),
    ("h3", "Freeze dependency versions during release week.", "expired", "Release manager", "2026-09-30", "Expired after the Q3 release and was not renewed."),
    ("h4", "Public API changes need a changelog entry.", "approved", "API guild lead", "2026-09-12", "6 sessions across 2 teams. Reviewers kept asking for it by hand."),
    ("h5", "Prefer dataclasses over plain dicts.", "rejected", "Tech lead, Identity", "2026-09-03", "Two developers on one team. Revisit if it spreads."),
    ("h6", "Use the repo's HTTP client. No new HTTP libraries.", "approved", "Tech lead, Payments", "2026-08-21", "7 sessions across 3 teams. First policy to reach a hard gate."),
]

# What a reviewer needs to decide on a candidate beyond the quotes (last 8 weeks of sessions, a 90-day PR replay).
# "c-P-07" is the brief a revised P-07 reopens with; the others belong to the seeded candidates.
BRIEFS = {'c-P-07': {'proposed': 14,
            'teams': [{'team': 'Payments', 'developers': 2, 'overruled': 3, 'accepted': 1},
                      {'team': 'Identity', 'developers': 2, 'overruled': 3, 'accepted': 2},
                      {'team': 'Search', 'developers': 2, 'overruled': 3, 'accepted': 2}],
            'areas': [{'area': 'tests/ with a placeholder issue link', 'n': 6}, {'area': 'tests/fixtures', 'n': 3}],
            'rework': {'turns': 33, 'hours': 2.7, 'prs': 5},
            'reach': {'repo': {'repos': 1, 'teams': 1, 'scanned': 31, 'flagged': 4, 'confirmed': 4},
                      'team': {'repos': 4, 'teams': 1, 'scanned': 52, 'flagged': 6, 'confirmed': 5},
                      'org': {'repos': 14, 'teams': 6, 'scanned': 168, 'flagged': 17, 'confirmed': 15}},
            'conflicts': [{'id': 'P-07',
                           'level': 'overlap',
                           'note': 'This replaces P-07. The current wording lets a placeholder issue link satisfy '
                                   'it, which is why it keeps being overridden. Approving retires P-07.'}],
            'recommend': {'action': 'approve',
                          'enforcement': 'gate',
                          'reason': 'The tightened wording would have been right 88% of the time. The only failures '
                                    'of P-07 are the placeholder-issue loophole.'}},
 'c1': {'proposed': 19,
        'teams': [{'team': 'Payments', 'developers': 3, 'overruled': 5, 'accepted': 1},
                  {'team': 'Identity', 'developers': 2, 'overruled': 3, 'accepted': 3},
                  {'team': 'Search', 'developers': 2, 'overruled': 3, 'accepted': 4}],
        'areas': [{'area': 'pyproject.toml / requirements.txt', 'n': 6},
                  {'area': 'package.json', 'n': 3},
                  {'area': 'go.mod', 'n': 2}],
        'rework': {'turns': 41, 'hours': 3.1, 'prs': 6},
        'reach': {'repo': {'repos': 1, 'teams': 1, 'scanned': 31, 'flagged': 6, 'confirmed': 6},
                  'team': {'repos': 4, 'teams': 1, 'scanned': 52, 'flagged': 9, 'confirmed': 8},
                  'org': {'repos': 14, 'teams': 6, 'scanned': 168, 'flagged': 21, 'confirmed': 18}},
        'conflicts': [{'id': 'P-04',
                       'level': 'overlap',
                       'note': 'P-04 already blocks new HTTP libraries in payments-service. This rule generalises it '
                               'to every dependency and every repo.'}],
        'recommend': {'action': 'approve',
                      'enforcement': 'check',
                      'reason': 'Overruled in most sessions across all three teams, and the check would have been '
                                'right 86% of the time. A hard gate would have blocked 3 PRs wrongly.'}},
 'c2': {'proposed': 14,
        'teams': [{'team': 'Payments', 'developers': 2, 'overruled': 3, 'accepted': 1},
                  {'team': 'Identity', 'developers': 2, 'overruled': 3, 'accepted': 2},
                  {'team': 'Search', 'developers': 1, 'overruled': 2, 'accepted': 3}],
        'areas': [{'area': 'tests/ (skip or xfail markers)', 'n': 5}, {'area': 'tests/fixtures', 'n': 3}],
        'rework': {'turns': 29, 'hours': 2.4, 'prs': 4},
        'reach': {'repo': {'repos': 1, 'teams': 1, 'scanned': 31, 'flagged': 3, 'confirmed': 3},
                  'team': {'repos': 4, 'teams': 1, 'scanned': 52, 'flagged': 4, 'confirmed': 4},
                  'org': {'repos': 14, 'teams': 6, 'scanned': 168, 'flagged': 12, 'confirmed': 11}},
        'conflicts': [{'id': 'P-07',
                       'level': 'conflict',
                       'note': 'P-07 already gates skipping a test without a linked issue, and 9 sessions overrode '
                               'it because a placeholder issue satisfies it. This rule is stricter. Approving it '
                               'should replace P-07, not sit beside it.'}],
        'recommend': {'action': 'approve',
                      'enforcement': 'gate',
                      'reason': 'The check would have been right 92% of the time, and the existing gate (P-07) is '
                                'being worked around. Replacing it closes the loophole.'}},
 'c3': {'proposed': 12,
        'teams': [{'team': 'Payments', 'developers': 2, 'overruled': 2, 'accepted': 3},
                  {'team': 'Search', 'developers': 1, 'overruled': 1, 'accepted': 6}],
        'areas': [{'area': 'Client / AsyncClient', 'n': 2}, {'area': 'Session / AsyncSession', 'n': 1}],
        'rework': {'turns': 9, 'hours': 0.7, 'prs': 2},
        'reach': {'repo': {'repos': 1, 'teams': 1, 'scanned': 31, 'flagged': 5, 'confirmed': 3},
                  'team': {'repos': 4, 'teams': 1, 'scanned': 52, 'flagged': 8, 'confirmed': 5},
                  'org': {'repos': 14, 'teams': 6, 'scanned': 168, 'flagged': 15, 'confirmed': 9}},
        'conflicts': [],
        'recommend': {'action': 'trial',
                      'enforcement': 'advice',
                      'reason': 'Only a quarter of proposals were overruled and the match is wrong 4 times in 10, so '
                                'a check would be noisy. Start as advice and see whether overrides fall.'}},
 'c4': {'proposed': 9,
        'teams': [{'team': 'Payments', 'developers': 1, 'overruled': 2, 'accepted': 2},
                  {'team': 'Search', 'developers': 1, 'overruled': 2, 'accepted': 3}],
        'areas': [{'area': 'Client.send / AsyncClient.send', 'n': 3}, {'area': 'transport/', 'n': 1}],
        'rework': {'turns': 14, 'hours': 1.1, 'prs': 3},
        'reach': {'repo': {'repos': 1, 'teams': 1, 'scanned': 31, 'flagged': 3, 'confirmed': 3},
                  'team': {'repos': 4, 'teams': 1, 'scanned': 52, 'flagged': 4, 'confirmed': 3},
                  'org': {'repos': 14, 'teams': 6, 'scanned': 168, 'flagged': 7, 'confirmed': 6}},
        'conflicts': [{'id': 'r5',
                       'level': 'overlap',
                       'note': 'The skill rule "Retry at the lowest transport layer" covers retries only. This rule '
                               'extends the same idea to timeouts and headers.'}],
        'recommend': {'action': 'trial',
                      'enforcement': 'advice',
                      'reason': 'Placement is a judgement call, so a mechanical check will miss cases. Two '
                                'developers agree. Publish as advice and review in 30 days.'}},
 'c5': {'proposed': 6,
        'teams': [{'team': 'Identity', 'developers': 1, 'overruled': 2, 'accepted': 4}],
        'areas': [{'area': 'auth/ (renames)', 'n': 2}],
        'rework': {'turns': 4, 'hours': 0.3, 'prs': 1},
        'reach': {'repo': {'repos': 1, 'teams': 1, 'scanned': 31, 'flagged': 5, 'confirmed': 3},
                  'team': {'repos': 4, 'teams': 1, 'scanned': 52, 'flagged': 5, 'confirmed': 3},
                  'org': {'repos': 14, 'teams': 6, 'scanned': 168, 'flagged': 5, 'confirmed': 3}},
        'conflicts': [],
        'recommend': {'action': 'wait',
                      'enforcement': 'advice',
                      'reason': 'One developer on one team. This is a preference until a second developer makes the '
                                'same correction.'}}}

# Health of the seeded policies: target, weekly overrides per 100 sessions since approval, and how often reviewers
# overrode the check (flagged, wrong). Advice-only policies have no check.
POLICY_HEALTH = {
    "P-09": {"target": 2, "weekly": [9, 7, 5, 4, 3, 2, 2, 2], "checks": (14, 1)},
    "P-07": {"target": 5, "weekly": [14, 13, 12, 11, 10, 10, 9, 9], "checks": (31, 9)},
    "P-05": {"target": 2, "weekly": [6, 5, 4, 4, 3, 3, 3, 3], "checks": None},
    "P-04": {"target": 1, "weekly": [7, 4, 3, 2, 1, 1, 1, 1], "checks": (12, 0)},
}


def _days_before(n: int) -> date:
    return ANCHOR - timedelta(days=n)


async def seed_dashboard(db: AsyncSession) -> None:
    """Empties the dashboard tables and loads the dummy rows. The caller commits."""
    await db.execute(text(f"TRUNCATE {', '.join(DASHBOARD_TABLES)} CASCADE"))

    for i in range(len(EXEC_ADHERENCE)):
        db.add(ExecWeek(
            week_start=EXEC_START + timedelta(weeks=i), adherence=EXEC_ADHERENCE[i],
            repeat_overrides=float(EXEC_REPEAT[i]), human_decisions=EXEC_HUMAN_PER_WEEK[i],
            mix={t: EXEC_MIX[t][i] for t in TYPES},
        ))
    for row in EXEC_PERIODS:
        (period, adh, adh_d, ov, ov_before, ver, ver_d, unreq, unreq_d, pend, oldest, sessions, first, missed, thin) = row
        db.add(ExecPeriod(
            period=period, adherence=adh, adherence_delta=adh_d, override=ov, override_before=ov_before,
            verified=ver, verified_delta=ver_d, unrequested=unreq, unrequested_delta=unreq_d,
            pending=pend, pending_oldest_days=oldest, sessions=sessions,
            rework_first=first, rework_missed=missed, rework_thin=thin,
        ))
    for pos, (kind, label, pct) in enumerate(EXEC_HUMAN_KINDS):
        db.add(ExecHumanKind(kind=kind, label=label, pct=pct, position=pos))
    for policy_id, week, text_, headline in EXEC_POLICY_EVENTS:
        db.add(ExecPolicyEvent(id=policy_id, week_start=EXEC_START + timedelta(weeks=week), text=text_, headline=headline))
    for pos, (name, tool, decisions, verified, unrequested, attempts, autonomy) in enumerate(EXEC_AGENTS):
        db.add(ExecAgent(name=name, tool=tool, decisions=decisions, verified=verified,
                         unrequested=unrequested, attempts=attempts, autonomy=autonomy, position=pos))
    await db.flush()

    for pos, t in enumerate(TEAMS):
        f = t["funnel"]
        db.add(Team(
            id=t["id"], name=t["name"], position=pos, prs=t["pr_count"], prs_delta=t["prs_delta"],
            attempts=t["attempts"], attempts_delta=t["attempts_delta"], overrules=t["overrules"],
            thin=t["thin"], unsupported=t["unsupported"],
            funnel_total=f[0], funnel_first=f[1], funnel_second_agent=f[2], funnel_second_thin=f[3],
            funnel_third_agent=f[4], funnel_third_thin=f[5],
        ))
    await db.flush()

    for t in TEAMS:
        for pos, (path, attempts, overrules) in enumerate(t["areas"]):
            area = TeamArea(team_id=t["id"], path=path, position=pos)
            db.add(area)
            await db.flush()
            for w in range(8):
                db.add(TeamAreaWeek(area_id=area.id, week_start=TEAM_START + timedelta(weeks=w),
                                    attempts=attempts[w], overrules=overrules[w]))
        for pos, (cause, body, prs) in enumerate(t["suggestions"]):
            db.add(TeamSuggestion(team_id=t["id"], position=pos, cause=cause, text=body, prs=prs))
        for kind, agent, human in t["mix"]:
            db.add(TeamMix(team_id=t["id"], type=kind, agent=agent, human=human))
        for name, calls, tokens in t["tools"]:
            db.add(TeamTool(team_id=t["id"], name=name, calls=calls, tokens=tokens))
        for number, title, area, week, agent, a, h, overrules, attempts, flags in t["prs"]:
            db.add(TeamPR(
                number=number, team_id=t["id"], title=title, area=area, week_start=TEAM_START + timedelta(weeks=week),
                agent=agent, agent_decisions=a, human_decisions=h, overrules=overrules, attempts=attempts, flags=flags,
            ))
    await db.flush()

    for pos, (item_id, kind, question, rows) in enumerate(CONSISTENCY):
        db.add(ConsistencyItem(id=item_id, type=kind, question=question, position=pos))
        for team_id, approach, prs in rows:
            db.add(ConsistencyRow(item_id=item_id, team_id=team_id, approach=approach, prs=prs))
    await db.flush()

    for c in CANDIDATES:
        db.add(GovCandidate(
            id=c["id"], pid=c["pid"], statement=c["statement"], type=c["type"], sessions=c["sessions"],
            teams=c["teams"], developers=c["developers"], trend=c["trend"], per_hundred=c["per_hundred"],
            match=c["match"], scope=c["scope"], enforcement=c["enforcement"], owner=c["owner"],
            expires=_d(c["expires"]), first_seen=_days_before(c["first_seen"]), status="open", brief=BRIEFS.get(c["id"]),
        ))
    for p in POLICIES:
        rec = p["recurrence"]
        health = POLICY_HEALTH[p["id"]]
        db.add(GovPolicy(
            id=p["id"], statement=p["statement"], type=p["type"], scope=p["scope"], scope_name=p["scope_name"],
            enforcement=p["enforcement"], owner=p["owner"], expires=_d(p["expires"]), adherence=p["adherence"],
            before=p["before"], after=p["after"], match=p["match"],
            recurrence_sessions=rec[0] if rec else None, recurrence_teams=rec[1] if rec else None,
            recurrence_developers=rec[2] if rec else None, status="active", published_on=_d(p["published_on"]),
            target=health["target"], weekly=health["weekly"],
            checks_flagged=health["checks"][0] if health["checks"] else None,
            checks_wrong=health["checks"][1] if health["checks"] else None,
        ))
    await db.flush()

    for c in CANDIDATES:
        for n, (eid, session, pr, team, dev, turn, kind, when, proposal, choice, quote) in enumerate(c["evidence"]):
            db.add(GovEvidence(id=eid, candidate_id=c["id"], position=n, session=session, pr=pr, team=team, dev=dev,
                               turn=turn, kind=kind, occurred_on=_d(when), proposal=proposal, choice=choice, quote=quote))
    for p in POLICIES:
        for n, (eid, session, pr, team, dev, turn, kind, when, proposal, choice, quote) in enumerate(p.get("evidence", [])):
            db.add(GovEvidence(id=eid, policy_id=p["id"], position=n, session=session, pr=pr, team=team, dev=dev,
                               turn=turn, kind=kind, occurred_on=_d(when), proposal=proposal, choice=choice, quote=quote))
    await db.flush()

    for pos, (rid, text_, skill, followed, violated, trend, latest_pr, latest_turn) in enumerate(SKILL_RULES):
        db.add(GovSkillRule(id=rid, position=pos, text=text_, skill=skill, followed=followed, violated=violated,
                            trend=trend, latest_pr=latest_pr, latest_turn=latest_turn))
    # The list shows newest first, so insert oldest first and let seq (identity) order it.
    for hid, statement, outcome, role, when, why in reversed(HISTORY):
        db.add(GovHistory(id=hid, statement=statement, outcome=outcome, role=role, occurred_on=_d(when), why=why))
    await db.flush()


async def _main() -> None:
    async with session_scope() as db:
        await seed_dashboard(db)
    print("dashboard seeded")
    from .pipeline.rollup import rollup_measured  # the seed wipes measured rows, so rebuild them from decisions
    print("measured rollup:", await rollup_measured())


if __name__ == "__main__":
    asyncio.run(_main())
