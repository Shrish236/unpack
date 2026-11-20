"""The decision brief, policy health and the watch / renew / relax actions on the governance inbox."""

from __future__ import annotations

from datetime import date, timedelta

from .test_dashboard import _today, seeded, viewer_client  # noqa: F401  (fixtures)

BASE = {"statement": "Rule.", "scope": "org", "enforcement": "check", "owner": "@platform", "expires": "2027-03-01"}


async def test_seeded_candidates_carry_a_brief_and_policies_carry_health(viewer_client):
    body = (await viewer_client.get("/api/governance")).json()
    c1 = next(c for c in body["candidates"] if c["id"] == "c1")
    assert c1["brief"]["proposed"] == 19 and c1["brief"]["recommend"]["enforcement"] == "check"
    assert set(c1["brief"]["reach"]) == {"repo", "team", "org"}
    assert c1["brief"]["conflicts"][0]["id"] == "P-04"
    p07 = next(p for p in body["policies"] if p["id"] == "P-07")
    assert (p07["target"], p07["checks"], p07["approved"]) == (5, {"flagged": 31, "wrong": 9}, "2026-09-03")
    assert p07["weekly"][-1] == 9 and p07["review"] is None
    assert next(p for p in body["policies"] if p["id"] == "P-05")["checks"] is None


async def test_approve_stores_the_target_and_review_date(viewer_client):
    review = (_today() + timedelta(days=30)).isoformat()
    body = (await viewer_client.post("/api/governance/candidates/c1/approve", json={**BASE, "target": 4, "review": review})).json()
    p = next(p for p in body["policies"] if p["id"] == "P-12")
    assert (p["target"], p["review"], p["approved"]) == (4, review, _today().isoformat())
    assert p["weekly"] is None and p["checks"] is None  # still measuring
    assert "Target: 4" in body["history"][0]["why"]


async def test_review_must_fall_between_today_and_expiry(viewer_client):
    early = (_today() - timedelta(days=1)).isoformat()
    assert (await viewer_client.post("/api/governance/candidates/c1/approve", json={**BASE, "review": early})).status_code == 400
    late = await viewer_client.post("/api/governance/candidates/c1/approve", json={**BASE, "review": "2028-01-01"})
    assert late.status_code == 400


async def test_watch_keeps_the_candidate_open_and_logs_it(viewer_client):
    body = (await viewer_client.post("/api/governance/candidates/c5/watch")).json()
    assert "c5" in [c["id"] for c in body["candidates"]]
    assert (body["history"][0]["outcome"], body["history"][0]["id"]) == ("watching", "h-P-16-w1")
    again = (await viewer_client.post("/api/governance/candidates/c5/watch")).json()
    assert again["history"][0]["id"] == "h-P-16-w2"
    assert (await viewer_client.post("/api/governance/candidates/nope/watch")).status_code == 404


async def test_renew_adds_six_months(viewer_client):
    body = (await viewer_client.post("/api/governance/policies/P-05/renew")).json()
    assert next(p for p in body["policies"] if p["id"] == "P-05")["expires"] == (date(2026, 12, 18) + timedelta(days=180)).isoformat()
    assert body["history"][0]["why"].startswith("Renewed to")
    assert (await viewer_client.post("/api/governance/policies/P-99/renew")).status_code == 404


async def test_relax_steps_enforcement_down_and_stops_at_advice(viewer_client):
    def pol(body, pid):
        return next(p for p in body["policies"] if p["id"] == pid)
    body = (await viewer_client.post("/api/governance/policies/P-04/relax")).json()
    assert pol(body, "P-04")["enforcement"] == "check" and pol(body, "P-04")["checks"] is not None
    body = (await viewer_client.post("/api/governance/policies/P-04/relax")).json()
    assert pol(body, "P-04")["enforcement"] == "advice" and pol(body, "P-04")["checks"] is None
    again = await viewer_client.post("/api/governance/policies/P-04/relax")
    assert (again.status_code, again.json()["error"]["code"]) == (409, "already_advice")
    assert (await viewer_client.post("/api/governance/policies/P-99/relax")).status_code == 404


async def test_revise_reopens_with_a_brief(viewer_client):
    body = (await viewer_client.post("/api/governance/policies/P-07/revise")).json()
    brief = next(c for c in body["candidates"] if c["id"] == "c-P-07")["brief"]
    assert brief["conflicts"][0]["id"] == "P-07" and brief["recommend"]["action"] == "approve"
