"""Dashboard reads and governance actions, against the dummy data from server/app/dashboard_seed.py."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from server.app.config import settings
from server.app.dashboard_seed import seed_dashboard
from server.app.db import session_scope


@pytest.fixture
async def seeded(db_ready):
    async with session_scope() as db:
        await seed_dashboard(db)


@pytest.fixture
async def viewer_client(client, monkeypatch, seeded):
    monkeypatch.setattr(settings, "DEV_VIEWER_LOGIN", "dev")
    return client


def _today() -> date:
    return datetime.now(timezone.utc).date()


async def test_dashboard_routes_need_a_login(client, seeded):
    for path in ("/api/dashboard/exec", "/api/dashboard/teams", "/api/dashboard/teams/payments", "/api/governance"):
        assert (await client.get(path)).status_code == 401, path


async def test_exec_30d_shows_five_weeks_and_its_window_of_events(viewer_client):
    body = (await viewer_client.get("/api/dashboard/exec?period=30d")).json()
    assert body["period"] == "30d"
    assert len(body["weeks"]) == 5
    assert body["weeks"][-1] == "2026-11-16"
    assert len(body["adherence"]) == len(body["repeat_overrides"]) == len(body["human_per_week"]) == 5
    assert set(body["mix"]) == {"architecture", "design", "dependency", "retries", "test", "scope"}
    assert all(len(v) == 5 for v in body["mix"].values())
    # P-09 is published before the window, so only P-12 and P-14 are drawn
    assert [e["id"] for e in body["policy_events"]] == ["P-12", "P-14"]
    assert [e["week"] for e in body["policy_events"]] == [0, 3]
    assert body["kpis"]["adherence"] == {"v": 86, "d": 5}
    assert body["kpis"]["sessions"] == 912
    assert body["rework"] == {"first": 71, "missed": 38, "thin": 31}
    assert body["headline"] == {"id": "P-12", "before": 11.0, "after": 3.0}


async def test_exec_90d_shows_all_twelve_weeks(viewer_client):
    body = (await viewer_client.get("/api/dashboard/exec?period=90d")).json()
    assert len(body["weeks"]) == 12
    assert body["weeks"][0] == "2026-08-31"
    assert body["kpis"]["override"] == {"v": 5.6, "before": 11.8}
    assert [e["id"] for e in body["policy_events"]] == ["P-09", "P-12", "P-14"]


async def test_exec_backlog_and_expiring_come_from_governance(viewer_client):
    body = (await viewer_client.get("/api/dashboard/exec")).json()
    # the three open candidates with the most developers, ties broken by sessions
    assert [b["id"] for b in body["backlog"]] == ["P-12", "P-13", "P-15"]
    assert body["backlog"][0]["waiting_days"] == (_today() - date(2026, 11, 16)).days  # seeded 4 days before the anchor
    for item in body["expiring"]:
        assert 0 <= item["in_days"] <= 90
    assert body["agents"][3] == {"name": "Claude Code", "tool": "adapter on the roadmap", "decisions": None,
                                 "verified": None, "unrequested": None, "attempts": None, "autonomy": None}


async def test_exec_rejects_an_unknown_period(viewer_client):
    response = await viewer_client.get("/api/dashboard/exec?period=7d")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_payload"


async def test_teams_index_lists_teams_and_consistency(viewer_client):
    body = (await viewer_client.get("/api/dashboard/teams")).json()
    assert [t["id"] for t in body["teams"]] == ["payments", "auth", "search"]
    assert [i["id"] for i in body["consistency"]] == ["retries", "timeouts", "flaky"]
    retries = body["consistency"][0]
    assert [r["team"] for r in retries["rows"]] == ["payments", "auth", "search"]


async def test_team_page_has_weeks_areas_funnel_and_prs(viewer_client):
    body = (await viewer_client.get("/api/dashboard/teams/payments")).json()
    assert body["name"] == "Payments"
    assert len(body["weeks"]) == 8
    assert body["weeks"][-1] == "2026-11-16"
    assert body["kpis"]["prs"] == 38
    assert body["kpis"]["prs_delta"] == "+6"
    assert [a["path"] for a in body["areas"]][:2] == ["payments/client", "payments/ledger"]
    assert all(len(a["attempts"]) == 8 == len(a["overrules"]) for a in body["areas"])
    assert body["funnel"] == {"total": 112, "first": 61, "second": {"agent": 29, "thin": 22}, "third": {"agent": 9, "thin": 5}}
    first_pr = body["prs"][0]
    assert first_pr["number"] == 482
    assert first_pr["week"] == 7
    assert first_pr["flags"] == ["unsupported", "new-dependency", "skipped-test"]
    assert body["tools"][0] == {"name": "read_file", "calls": 1480, "tokens": 1_310_000}
    assert body["mix"][0] == {"type": "architecture", "agent": 31, "human": 6}


async def test_unknown_team_is_not_found(viewer_client):
    assert (await viewer_client.get("/api/dashboard/teams/nobody")).status_code == 404


async def test_governance_inbox_has_candidates_policies_rules_and_history(viewer_client):
    body = (await viewer_client.get("/api/governance")).json()
    assert body["today"] == _today().isoformat()
    assert [c["id"] for c in body["candidates"]] == ["c1", "c2", "c4", "c3", "c5"]
    assert [p["id"] for p in body["policies"]] == ["P-09", "P-07", "P-05", "P-04"]
    p07 = next(p for p in body["policies"] if p["id"] == "P-07")
    assert p07["recurrence"]["sessions"] == 9
    assert [e["id"] for e in p07["recurrence"]["evidence"]] == ["e20"]
    assert next(p for p in body["policies"] if p["id"] == "P-09")["recurrence"] is None
    assert len(body["rules"]) == 6
    assert [h["id"] for h in body["history"]][:2] == ["h1", "h2"]
    assert body["candidates"][0]["evidence"][0]["when"] == "2026-11-19"


async def test_approve_publishes_a_policy_and_records_it(viewer_client):
    response = await viewer_client.post("/api/governance/candidates/c1/approve", json={
        "statement": "Add no new runtime dependency without approval.", "scope": "org",
        "enforcement": "gate", "owner": "@platform", "expires": "2027-03-01",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert "c1" not in [c["id"] for c in body["candidates"]]
    published = next(p for p in body["policies"] if p["id"] == "P-12")
    assert published["enforcement"] == "gate"
    assert published["scope_name"] == "Org"
    assert published["before"] == 11
    assert body["history"][0]["outcome"] == "approved"
    assert body["history"][0]["id"] == "h-P-12"


async def test_an_approved_candidate_cannot_be_decided_again(viewer_client):
    payload = {"statement": "x", "scope": "repo", "enforcement": "advice", "owner": "@platform", "expires": "2027-03-01"}
    assert (await viewer_client.post("/api/governance/candidates/c3/approve", json=payload)).status_code == 200
    again = await viewer_client.post("/api/governance/candidates/c3/reject", json={"reason": "changed my mind"})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "not_open"


async def test_approve_checks_owner_scope_and_expiry(viewer_client):
    base = {"statement": "Rule.", "scope": "org", "enforcement": "check", "owner": "@platform", "expires": "2027-03-01"}
    bad_owner = await viewer_client.post("/api/governance/candidates/c1/approve", json={**base, "owner": "platform"})
    assert bad_owner.status_code == 400
    bad_scope = await viewer_client.post("/api/governance/candidates/c1/approve", json={**base, "scope": "everyone"})
    assert bad_scope.status_code == 400
    past = await viewer_client.post("/api/governance/candidates/c1/approve", json={**base, "expires": "2020-01-01"})
    assert past.status_code == 400
    blank = await viewer_client.post("/api/governance/candidates/c1/approve", json={**base, "statement": "   "})
    assert blank.status_code == 400
    missing = await viewer_client.post("/api/governance/candidates/nope/approve", json=base)
    assert missing.status_code == 404


async def test_reject_keeps_the_reason_in_history(viewer_client):
    response = await viewer_client.post("/api/governance/candidates/c2/reject", json={"reason": "One team's preference."})
    assert response.status_code == 200
    body = response.json()
    assert "c2" not in [c["id"] for c in body["candidates"]]
    rejected = body["history"][0]
    assert rejected["outcome"] == "rejected"
    assert rejected["why"] == "One team's preference."


async def test_reject_without_a_reason_says_so(viewer_client):
    body = (await viewer_client.post("/api/governance/candidates/c2/reject", json={})).json()
    assert body["history"][0]["why"] == "No reason given."


async def test_retire_removes_an_active_policy_and_logs_it(viewer_client):
    body = (await viewer_client.post("/api/governance/policies/P-05/retire")).json()
    assert "P-05" not in [p["id"] for p in body["policies"]]
    assert body["history"][0]["outcome"] == "expired"
    assert body["history"][0]["role"] == "Policy owner"
    assert (await viewer_client.post("/api/governance/policies/P-05/retire")).status_code == 404


async def test_revise_reopens_a_recurring_policy_as_a_candidate(viewer_client):
    body = (await viewer_client.post("/api/governance/policies/P-07/revise")).json()
    assert "P-07" not in [p["id"] for p in body["policies"]]
    reopened = next(c for c in body["candidates"] if c["id"] == "c-P-07")
    assert reopened["pid"] == "P-07b"
    assert reopened["sessions"] == 9
    assert reopened["evidence"][0]["id"] == "e20-c-P-07"

    approved = await viewer_client.post("/api/governance/candidates/c-P-07/approve", json={
        "statement": "Never skip or delete a failing test. Link an open issue.", "scope": "org",
        "enforcement": "gate", "owner": "@quality", "expires": "2027-06-30",
    })
    assert approved.status_code == 200, approved.text
    assert "P-07b" in [p["id"] for p in approved.json()["policies"]]


async def test_only_a_recurring_policy_can_be_revised(viewer_client):
    response = await viewer_client.post("/api/governance/policies/P-05/revise")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_recurrence"
