"""Design gaps and operational paths: reconciler edge cases, installation webhooks, admin rebuild, OAuth
single use, revoked tokens, internal-only render, rate limits, job retries and worker failure, heartbeats."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select, text, update

from server.app import services
from server.app.config import settings
from server.app.db import session_scope
from server.app.jobs.reconciler import reconcile_once
from server.app.jobs.worker import job_slot
from server.app.models import Analysis, Job, PullRequest, Push, Repo, TrackedBranch, WebSession
from server.app.pipeline import repos as repos_module

from .conftest import Origin, drain_jobs
from .helpers import create_repo, gzip_json, ingest_headers, origin_payload, standard_files
from .test_ingest_and_analysis import login, post_ingest
from .test_publish_and_reconcile import pr_for

B_SHA = "b" * 40


@pytest.fixture
def origin(tmp_path):
    base, head = standard_files()
    return Origin(tmp_path, base, head)


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(settings.GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


async def force_due():
    async with session_scope() as session:
        await session.execute(update(TrackedBranch).values(next_check_at=datetime.now(timezone.utc) - timedelta(seconds=1)))


async def second_push(client, token, origin, head=B_SHA):
    payload = origin_payload(origin)
    payload["head_sha"] = head
    payload["commits"] = [{"sha": head, "message": "second", "author_time": "2026-11-19T15:00:00Z"}]
    response = await client.post("/v1/ingest", content=gzip_json(payload), headers=ingest_headers(token))
    assert response.status_code == 202, response.text
    return response.json()


# ---- reconciler -----------------------------------------------------------------

async def test_needs_publish_clears_once_the_latest_analysis_is_shown(client, tmp_data_dir, origin, fake_github):
    _, token = await create_repo(remote_url=origin.remote_url)
    await post_ingest(client, token, origin_payload(origin))
    await drain_jobs()
    fake_github.open_prs = [pr_for(origin)]
    await reconcile_once()
    await drain_jobs()
    async with session_scope() as session:
        tracked = (await session.execute(select(TrackedBranch))).scalar_one()
        assert tracked.needs_publish is False


async def test_pr_behind_an_older_analysis_publishes_the_ancestor(client, tmp_data_dir, origin, fake_github):
    _, token = await create_repo(remote_url=origin.remote_url)
    await post_ingest(client, token, origin_payload(origin))
    await drain_jobs()
    await second_push(client, token, origin)  # the newest push, not yet on GitHub
    await drain_jobs()
    async with session_scope() as session:
        newest = (await session.execute(select(Push).where(Push.head_sha == B_SHA))).scalar_one()
        newest.received_at = datetime.now(timezone.utc) - timedelta(minutes=20)  # past the 10-minute wait
    fake_github.open_prs = [pr_for(origin, head_sha=origin.base_sha)]
    fake_github.compare_status[B_SHA] = {"status": "ahead", "ahead_by": 1, "behind_by": 0}
    fake_github.compare_status[origin.base_sha] = {"status": "ahead", "ahead_by": 1, "behind_by": 0}
    await reconcile_once()
    await drain_jobs()
    assert len(fake_github.created) == 1
    body = fake_github.created[0]["body"]
    assert f"Covers up to {origin.head_sha[:7]}; the newest push is not on GitHub yet." in body


async def test_closed_pull_request_moves_the_branch_to_closed_recently(client, tmp_data_dir, origin, fake_github):
    _, token = await create_repo(remote_url=origin.remote_url)
    await post_ingest(client, token, origin_payload(origin))
    await drain_jobs()
    fake_github.open_prs = [pr_for(origin)]
    await reconcile_once()
    await drain_jobs()
    fake_github.open_prs = []
    fake_github.pr_state[7] = {"state": "closed", "merged_at": "2026-11-20T10:00:00Z"}
    await force_due()
    await reconcile_once()
    async with session_scope() as session:
        pr = (await session.execute(select(PullRequest))).scalar_one()
        tracked = (await session.execute(select(TrackedBranch))).scalar_one()
        assert pr.state == "merged"
        assert tracked.status == "closed_recently"


async def test_stale_branch_without_a_pull_request_is_abandoned(client, tmp_data_dir, origin, fake_github):
    _, token = await create_repo(remote_url=origin.remote_url)
    await post_ingest(client, token, origin_payload(origin))
    await drain_jobs()
    async with session_scope() as session:
        push = (await session.execute(select(Push))).scalar_one()
        push.received_at = datetime.now(timezone.utc) - timedelta(days=8)
    fake_github.open_prs = []
    await reconcile_once()
    async with session_scope() as session:
        assert (await session.execute(select(TrackedBranch))).scalar_one().status == "abandoned"


# ---- ingest --------------------------------------------------------------------

async def test_push_rate_limit_answers_429_with_retry_after(client, tmp_data_dir, origin, monkeypatch):
    monkeypatch.setattr(settings, "PUSHES_PER_MINUTE_PER_REPO", 1)
    _, token = await create_repo(remote_url=origin.remote_url)
    assert (await post_ingest(client, token, origin_payload(origin))).status_code == 202
    response = await client.post("/v1/ingest", content=gzip_json({**origin_payload(origin), "head_sha": B_SHA}),
                                 headers=ingest_headers(token))
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    assert response.json()["error"]["code"] == "rate_limited"


async def test_disabled_repo_is_refused_without_an_install_link(client, tmp_data_dir, origin):
    _, token = await create_repo(remote_url=origin.remote_url, status="disabled")
    response = await post_ingest(client, token, origin_payload(origin))
    assert response.status_code == 409
    assert response.json()["error"] == {"code": "repo_disabled",
                                        "message": "repository is disabled or the GitHub App is not installed",
                                        "details": {}}


# ---- webhooks and setup -------------------------------------------------------------

async def _webhook(client, event: str, payload: dict, delivery: str):
    body = json.dumps(payload).encode()
    return await client.post("/github/webhook", content=body, headers={
        "X-GitHub-Event": event, "X-GitHub-Delivery": delivery, "X-Hub-Signature-256": sign(body)})


async def test_installation_deleted_marks_its_repos_app_missing(client, tmp_data_dir, origin, fake_github):
    await create_repo(remote_url=origin.remote_url, installation_id=123)
    response = await _webhook(client, "installation", {"action": "deleted", "installation": {"id": 123}}, "i1")
    assert response.status_code == 204
    async with session_scope() as session:
        repo = (await session.execute(select(Repo))).scalar_one()
        assert repo.status == "app_missing" and repo.installation_id is None


async def test_repositories_removed_and_added_update_the_repo(client, tmp_data_dir, origin, fake_github):
    await create_repo(remote_url=origin.remote_url, installation_id=123)
    await _webhook(client, "installation_repositories",
                   {"action": "removed", "installation": {"id": 123},
                    "repositories_removed": [{"full_name": "o/r"}]}, "i2")
    async with session_scope() as session:
        assert (await session.execute(select(Repo))).scalar_one().status == "app_missing"
    await _webhook(client, "installation_repositories",
                   {"action": "added", "installation": {"id": 123},
                    "repositories_added": [{"full_name": "o/r"}]}, "i3")
    async with session_scope() as session:
        assert (await session.execute(select(Repo))).scalar_one().status == "active"


async def test_setup_page_links_installed_repositories(client, tmp_data_dir, origin, fake_github):
    await create_repo(remote_url=origin.remote_url, installation_id=None, status="app_missing")
    fake_github.installation_repos = [{"full_name": "o/r"}]
    response = await client.get("/github/setup?installation_id=123&setup_action=install")
    assert response.status_code == 200
    assert "<li>o/r</li>" in response.text and "unpack install" in response.text
    async with session_scope() as session:
        repo = (await session.execute(select(Repo))).scalar_one()
        assert repo.installation_id == 123 and repo.status == "active"


# ---- admin -------------------------------------------------------------------------

async def test_admin_rebuild_builds_and_caches_the_graph(client, tmp_data_dir, origin, fake_github):
    repo_id, _ = await create_repo(remote_url=origin.remote_url)
    admin = {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    response = await client.post(f"/admin/repos/{repo_id}/graph/rebuild", json={"sha": origin.base_sha}, headers=admin)
    assert response.status_code == 202
    assert await drain_jobs() == 1
    assert repos_module.load_cached_graph(repo_id, origin.base_sha) is not None
    async with session_scope() as session:
        assert (await session.execute(select(Repo))).scalar_one().graph_built_sha == origin.base_sha


async def test_every_admin_endpoint_rejects_a_wrong_token(client):
    wrong = {"Authorization": "Bearer nope"}
    checks = [
        ("POST", "/admin/repos", {"owner": "o", "name": "x"}),
        ("POST", "/admin/repos/1/rotate-token", None),
        ("POST", "/admin/repos/1/graph/rebuild", None),
        ("GET", "/admin/jobs", None),
        ("POST", "/admin/analyses/abc/retry", None),
        ("GET", "/admin/tracked-branches", None),
        ("POST", "/admin/tracked-branches/1/check-now", None),
    ]
    for method, path, body in checks:
        response = await client.request(method, path, json=body, headers=wrong)
        assert response.status_code == 401, path


# ---- login and sessions ---------------------------------------------------------------

async def test_oauth_state_is_accepted_once(client, fake_github):
    def oauth(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "gho_once"})

    services.set_oauth_transport(httpx.MockTransport(oauth))
    try:
        login_response = await client.get("/auth/login?next=/a/abc", follow_redirects=False)
        state = dict(p.split("=", 1) for p in login_response.headers["location"].split("?", 1)[1].split("&"))["state"]
        first = await client.get(f"/auth/callback?code=x&state={state}", follow_redirects=False)
        assert first.status_code == 302
        replay = await client.get(f"/auth/callback?code=x&state={state}", follow_redirects=False)
        assert replay.status_code == 400 and "Login failed" in replay.text
    finally:
        services.set_oauth_transport(None)


async def test_revoked_github_token_logs_the_viewer_out(client, tmp_data_dir, origin, fake_github):
    _, token = await create_repo(remote_url=origin.remote_url)
    public_id = (await post_ingest(client, token, origin_payload(origin))).json()["analysis"]["public_id"]
    await drain_jobs()
    await login(client)
    fake_github.viewer_access = 401
    response = await client.get(f"/api/analyses/{public_id}")
    assert response.status_code == 401 and response.json()["error"]["code"] == "not_logged_in"
    assert (await client.get("/api/me")).status_code == 401
    async with session_scope() as session:
        assert (await session.execute(select(WebSession))).first() is None


async def test_render_is_refused_to_public_clients(client, tmp_data_dir, monkeypatch):
    from server.app.security import render_token

    public = httpx.AsyncClient(transport=httpx.ASGITransport(app=client._transport.app, client=("8.8.8.8", 4321)),
                               base_url="https://unpack.test")
    token = render_token("abc123")
    response = await public.get(f"/render/abc123?render_token={token}")
    assert response.status_code == 403
    await public.aclose()


# ---- worker and health ------------------------------------------------------------------

async def test_failed_job_is_retried_then_marks_the_analysis_failed(client, tmp_data_dir, origin, fake_github):
    _, token = await create_repo(remote_url=origin.remote_url)
    public_id = (await post_ingest(client, token, origin_payload(origin))).json()["analysis"]["public_id"]
    async with session_scope() as session:
        push = (await session.execute(select(Push))).scalar_one()
        payload_path = push.payload_path
    import os

    os.remove(payload_path)  # the job cannot load its payload, so every attempt fails

    stop = asyncio.Event()
    slot = asyncio.create_task(job_slot(stop))
    try:
        for _ in range(100):  # first attempt: retry scheduled
            await asyncio.sleep(0.05)
            async with session_scope() as session:
                job = (await session.execute(select(Job).where(Job.type == "analyze_push"))).scalar_one()
                if job.attempts >= 1 and job.status == "queued":
                    break
        assert job.last_error and "FileNotFoundError" in job.last_error
        async with session_scope() as session:  # last attempt: the job is failed and the analysis too
            await session.execute(update(Job).values(attempts=Job.max_attempts, run_after=datetime.now(timezone.utc)))
        for _ in range(100):
            await asyncio.sleep(0.05)
            async with session_scope() as session:
                analysis = (await session.execute(select(Analysis).where(Analysis.public_id == public_id))).scalar_one()
                if analysis.status == "failed":
                    break
        assert analysis.error_code == "internal_error"
    finally:
        stop.set()
        await asyncio.wait_for(slot, 5)


async def test_readyz_is_unhealthy_when_the_worker_heartbeat_is_stale(client):
    async with session_scope() as session:
        await session.execute(text(
            "INSERT INTO worker_heartbeat (worker_id, beat_at) VALUES ('stale', now() - interval '5 minutes')"))
    response = await client.get("/readyz")
    assert response.status_code == 503 and response.json()["worker"] == "failing"


async def test_shared_browser_is_started_once_and_reused(tmp_data_dir):
    from server.app.jobs import render

    try:
        first = await render._shared_browser()
    except Exception as exc:  # no Chromium on this machine
        pytest.skip(f"Chromium is not available: {type(exc).__name__}")
    try:
        assert await render._shared_browser() is first
    finally:
        await render.shutdown_browser()


# ---- live API details ---------------------------------------------------------------

async def test_node_detail_reports_total_callers_and_unresolved_calls(client, tmp_data_dir, origin, fake_github):
    import urllib.parse

    _, token = await create_repo(remote_url=origin.remote_url)
    public_id = (await post_ingest(client, token, origin_payload(origin))).json()["analysis"]["public_id"]
    await drain_jobs()
    await login(client)
    node = urllib.parse.quote("pkg/core.py::helper", safe="")
    body = (await client.get(f"/api/analyses/{public_id}/nodes/{node}")).json()
    assert body["callers_total"] == len(body["callers"]) == 1
    assert body["callees_total"] == len(body["callees"])
    assert isinstance(body["unresolved_calls"], list)
    assert all({"line", "raw", "reason"} <= set(item) for item in body["unresolved_calls"])


async def test_map_folder_line_counts_are_the_sum_of_their_files(client, tmp_data_dir, origin, fake_github):
    _, token = await create_repo(remote_url=origin.remote_url)
    await post_ingest(client, token, origin_payload(origin))
    await drain_jobs()
    await login(client)
    rows = (await client.get(f"/api/repos/o/r/map?sha={origin.head_sha}")).json()["nodes"]
    folder = next(r for r in rows if r[0] == "pkg" and r[1] == "folder")
    files_under = [r for r in rows if r[1] == "file" and r[0].startswith("pkg/") and "/" not in r[0][4:]]
    assert folder[3] == sum(r[3] for r in files_under) and folder[3] > 0


async def test_map_and_edges_are_404_for_unknown_repositories(client, tmp_data_dir, origin, fake_github):
    await create_repo(remote_url=origin.remote_url)
    await login(client)
    assert (await client.get(f"/api/repos/o/nope/map?sha={origin.head_sha}")).status_code == 404
    assert (await client.get(f"/api/repos/o/r/nodes/x.py::f/edges?sha={origin.head_sha}")).status_code in (404, 503)
