"""Dashboard numbers measured from sessions: the metric definitions, and the routes that overlay them on the sample data."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import select

from server.app.config import settings
from server.app.dashboard_seed import seed_dashboard
from server.app.db import session_scope
from server.app.dev_fixtures import add_fake_sessions, clear_fake_sessions
from server.app.models import Decision, FunctionReason, TeamPR
from server.app.pipeline.metrics import exec_metrics, is_verified, rework_cause, rework_rounds, team_metrics, week_window
from server.app.pipeline.rollup import load_sessions, rollup_measured

TODAY = date(2026, 11, 20)  # a Friday; its week starts 2026-11-16


def x(i, actor="human", kind="reject", type_="dependency", statement="", followed=None):
    return NS(id=i, actor=actor, kind=kind, type=type_, statement=statement, rule_followed=followed)


def sess(sid, when, decisions, attempts=1, verified=True, flags=(), drivers=None, area="payments/client", model="m", agent="gemini-cli"):
    return {
        "analysis": NS(id=sid), "when": when, "decisions": decisions, "area": area, "model": model,
        "signals": {"attempts": attempts, "agent": agent, "flags": [{"flag": f} for f in flags],
                    "tool_stats": {"read_file": {"calls": 2, "tokens": 100}}},
        "facts": {"last_test_run": {"command": "pytest"} if verified else None, "tested_after_final_edit": verified},
        "drivers": Counter(drivers or {"user_asked": 2}),
    }


def test_week_window_ends_with_the_current_week():
    w = week_window(TODAY, 5)
    assert len(w) == 5 and w[-1] == date(2026, 11, 16) and w[0] == date(2026, 10, 19)


def test_nothing_in_the_window_gives_none():
    assert exec_metrics([], TODAY, 5) is None and team_metrics([], TODAY) is None
    old = [sess(1, date(2026, 1, 5), [])]
    assert exec_metrics(old, TODAY, 5) is None


def test_exec_numbers_and_definitions():
    same = "Do not add a runtime dependency for small helpers"
    data = [
        # last week: one rule followed, one violated; the same correction recurs in two sessions
        sess(1, date(2026, 11, 10), [x(1, "agent", "choice", followed=True), x(2, statement=same, followed=False)],
             attempts=2, flags=["unsupported"], drivers={"agent_decided": 1, "user_asked": 1}),
        sess(2, date(2026, 11, 18), [x(3, statement=same), x(4, kind="requirement", type_="test")], verified=True,
             drivers={"user_asked": 3}),
        sess(3, date(2026, 11, 19), [x(5, "agent", "choice", type_="design")], verified=False, model="m2"),
    ]
    m = exec_metrics(data, TODAY, 5)
    assert m["weeks"][-1] == "2026-11-16" and len(m["adherence"]) == 5
    assert m["adherence"][-2] == 50 and m["adherence"][-1] is None  # a week with no rule check has no value, not zero
    assert m["kpis"]["adherence"] == {"v": 50, "d": None}  # no earlier window to compare
    assert m["kpis"]["sessions"] == 3
    # Verified: session 1 has an unsupported flag, session 3 has no test run.
    assert m["kpis"]["verified"]["v"] == 33
    assert is_verified(data[1]) and not is_verified(data[0]) and not is_verified(data[2])
    # Unrequested: 1 agent-decided of 7 explained functions (1+1, 3, 2 default).
    assert m["kpis"]["unrequested"]["v"] == round(100 * 1 / 7)
    # The same correction in two sessions is a repeat: 2 decisions over 3 sessions.
    assert m["kpis"]["override"]["v"] == round(100 * 2 / 3, 1)
    # Rework: session 1 (2 attempts + override) and 2 (a requirement was added) needed it; 3 did not.
    assert rework_cause(data[0]) == "missed" and rework_cause(data[1]) == "thin" and rework_cause(data[2]) is None
    assert m["rework"] == {"first": 1, "missed": 1, "thin": 1}
    assert m["human_per_week"][-2:] == [1, 2]
    assert m["mix"]["dependency"][-1] == 1 and sum(sum(v) for v in m["mix"].values()) == 5
    kinds = {k["kind"]: k["pct"] for k in m["human_kinds"]}
    assert kinds["reject"] == 67 and kinds["requirement"] == 33
    assert {a["name"] for a in m["agents"]} == {"m", "m2"}


def test_delta_against_the_previous_window():
    data = [sess(1, date(2026, 10, 1), [x(1, "agent", "choice", followed=False)]),
            sess(2, date(2026, 11, 17), [x(2, "agent", "choice", followed=True)])]
    m = exec_metrics(data, TODAY, 5)
    assert m["kpis"]["adherence"] == {"v": 100, "d": 100}


def test_team_funnel_areas_and_tools():
    data = [
        sess(1, date(2026, 11, 17), [], area="a/x"),  # first time right
        sess(2, date(2026, 11, 17), [x(1)], area="a/x", attempts=2),  # one round, agent missed
        sess(3, date(2026, 11, 3), [x(2, kind="requirement"), x(3, kind="redirect"), x(4, kind="reject")], area="b/y"),  # 3 rounds, thin
    ]
    t = team_metrics(data, TODAY)
    f = t["funnel"]
    assert f == {"total": 3, "first": 1, "second": {"agent": 1, "thin": 0}, "third": {"agent": 0, "thin": 1}}
    assert rework_rounds(data[2]) == 3
    assert [a["path"] for a in t["areas"]] == ["a/x", "b/y"] and t["areas"][0]["overrules"][-1] == 1
    assert t["kpis"]["prs"] == 3 and t["kpis"]["thin"] == 33 and t["kpis"]["unsupported"] == 0
    assert t["tools"] == [{"name": "read_file", "calls": 6, "tokens": 300}]


@pytest.fixture
async def viewer_client(client, monkeypatch, db_ready):
    monkeypatch.setattr(settings, "DEV_VIEWER_LOGIN", "dev")
    async with session_scope() as db:
        await seed_dashboard(db)
    return client


async def test_routes_stay_sample_without_measured_sessions(viewer_client):
    body = (await viewer_client.get("/api/dashboard/exec")).json()
    assert set(body["sources"].values()) == {"sample"} and body["kpis"]["sessions"] == 912
    team = (await viewer_client.get("/api/dashboard/teams/payments")).json()
    assert team["sources"]["kpis"] == "sample" and team["kpis"]["prs"] == 38


async def test_routes_overlay_measured_sessions_with_fake_data(viewer_client):
    assert await add_fake_sessions(15, now=datetime.now(timezone.utc)) == 15
    await rollup_measured()
    body = (await viewer_client.get("/api/dashboard/exec?period=90d")).json()
    assert body["sources"]["trend"] == "measured" and body["sources"]["kpis"] == "measured"
    assert len(body["weeks"]) == 12 and len(body["adherence"]) == 12 and set(body["mix"]) >= {"dependency", "test"}
    assert body["kpis"]["sessions"] == 15 and body["kpis"]["pending"]["v"] >= 0
    assert sum(body["rework"].values()) == 15
    assert body["agents"] and all(a["name"] != "Claude Code" for a in body["agents"])
    # The 30 day window holds fewer sessions than the 90 day one.
    short = (await viewer_client.get("/api/dashboard/exec?period=30d")).json()
    assert short["kpis"]["sessions"] <= 15 and len(short["weeks"]) == 5

    team = (await viewer_client.get("/api/dashboard/teams/payments")).json()
    assert team["sources"]["kpis"] == "measured" and team["sources"]["suggestions"] == "sample"
    assert team["funnel"]["total"] <= 15 and len(team["weeks"]) == 8
    measured_prs = [p for p in team["prs"] if p["source"] == "measured"]
    assert measured_prs and all(p["public_id"] for p in measured_prs)
    assert all(p["week"] in range(-1, 8) for p in team["prs"])
    gov = (await viewer_client.get("/api/governance")).json()
    ev = [e for c in gov["candidates"] for e in c["evidence"] if e["source"] == "measured"]
    assert ev and all(e["public_id"] for e in ev)

    # Fake sessions go through the PR endpoint with the new fields.
    from server.app.models import Analysis
    async with session_scope() as db:
        public_id = (await db.execute(select(Analysis.public_id).limit(1))).scalar_one()
        decisions = (await db.execute(select(Decision))).scalars().all()
        assert decisions and all(d.outcome in ("ok", "overruled", "reverted", "rule_violated", "unverified") for d in decisions)
        assert (await db.execute(select(FunctionReason))).first() is not None
    assert (await clear_fake_sessions()) == 15
    await rollup_measured()
    async with session_scope() as db:
        assert (await load_sessions(db)) == []
        assert (await db.execute(select(TeamPR).where(TeamPR.source == "measured"))).first() is None
    assert public_id.startswith("fake")


async def test_threshold_keeps_sample_until_enough_sessions(viewer_client, monkeypatch):
    await add_fake_sessions(3)
    monkeypatch.setattr(settings, "METRICS_MIN_SESSIONS", 10)
    body = (await viewer_client.get("/api/dashboard/exec")).json()
    assert set(body["sources"].values()) == {"sample"}
