"""Admin (§5.7), OAuth login (§5.4) and the internal render route (§5.6). There are no webhooks: the poller replaces them."""

from __future__ import annotations

import json

import httpx
import pytest

from server.app import services
from server.app.config import settings
from server.app.db import session_scope
from server.app.security import render_token

from .conftest import Origin, drain_jobs
from .helpers import create_repo, gzip_json, ingest_headers, origin_payload, standard_files


@pytest.fixture
def origin(tmp_path):
    base, head = standard_files()
    return Origin(tmp_path, base, head)


async def test_admin_requires_token_and_creates_repos(client, fake_github):
    anon = await client.post("/admin/repos", json={"owner": "o", "name": "new"})
    assert anon.status_code == 401

    admin = {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    created = await client.post("/admin/repos", json={"owner": "o", "name": "new"}, headers=admin)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["ingest_token"].startswith("unp_") and body["installation_id"] == 123

    fake_github.installation_for["o/missing"] = None
    not_installed = await client.post("/admin/repos", json={"owner": "o", "name": "missing"}, headers=admin)
    assert not_installed.status_code == 409
    assert not_installed.json()["error"]["code"] == "app_not_installed"
    assert "installations/new" in not_installed.json()["error"]["details"]["install_url"]

    dup = await client.post("/admin/repos", json={"owner": "o", "name": "new"}, headers=admin)
    assert dup.status_code == 409

    rotated = await client.post(f"/admin/repos/{body['repo_id']}/rotate-token", headers=admin)
    assert rotated.status_code == 200 and rotated.json()["ingest_token"] != body["ingest_token"]


async def test_admin_jobs_retry_and_tracked_branches(client, tmp_data_dir, fake_github, origin):
    admin = {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    _, token = await create_repo(remote_url=origin.remote_url)
    response = await client.post("/v1/ingest", content=gzip_json(origin_payload(origin, with_head_content=False)),
                                 headers=ingest_headers(token))
    public_id = response.json()["analysis"]["public_id"]
    await drain_jobs()

    retry_done_guard = await client.post(f"/admin/analyses/{public_id}/retry", headers=admin)
    assert retry_done_guard.status_code == 202  # it failed, so retrying is allowed

    jobs = await client.get("/admin/jobs?type=analyze_push", headers=admin)
    assert jobs.status_code == 200 and jobs.json()["jobs"]

    branches = await client.get("/admin/tracked-branches", headers=admin)
    assert branches.json()["branches"][0]["branch"] == "feature/x"



async def test_retry_refused_when_not_failed(client, tmp_data_dir, fake_github, origin):
    admin = {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
    _, token = await create_repo(remote_url=origin.remote_url)
    response = await client.post("/v1/ingest", content=gzip_json(origin_payload(origin)), headers=ingest_headers(token))
    public_id = response.json()["analysis"]["public_id"]
    refused = await client.post(f"/admin/analyses/{public_id}/retry", headers=admin)
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "not_failed"


async def test_oauth_login_and_callback(client, fake_github):
    seen = {}

    def oauth(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"access_token": "gho_viewer_token"})

    services.set_oauth_transport(httpx.MockTransport(oauth))
    try:
        login = await client.get("/auth/login?next=/a/abc123", follow_redirects=False)
        assert login.status_code == 302
        location = login.headers["location"]
        assert location.startswith("https://github.com/login/oauth/authorize?")
        state = dict(p.split("=", 1) for p in location.split("?", 1)[1].split("&"))["state"]

        for evil in ("https://evil.test", "//evil.test", "/\\evil.test", "/%09/evil.test"):
            bad_next = await client.get(f"/auth/login?next={evil}", follow_redirects=False)
            assert bad_next.status_code == 400, evil

        bad = await client.get("/auth/callback?code=x&state=forged", follow_redirects=False)
        assert bad.status_code == 400 and "Login failed" in bad.text

        ok = await client.get(f"/auth/callback?code=abc&state={state}", follow_redirects=False)
        assert ok.status_code == 302 and ok.headers["location"] == "/a/abc123"
        assert seen["body"]["code"] == "abc"
        me = await client.get("/api/me")
        assert me.status_code == 200 and me.json()["login"] == "octo"

        await client.post("/auth/logout")
        logged_out = await client.get("/api/me")
        assert logged_out.status_code == 401

        # Login from a dashboard: no next goes home, and a hash route is kept through the callback.
        assert (await client.get("/auth/login", follow_redirects=False)).status_code == 302
        dash = await client.get("/auth/login?next=%2F%23%2Fteam", follow_redirects=False)
        dash_state = dict(p.split("=", 1) for p in dash.headers["location"].split("?", 1)[1].split("&"))["state"]
        back = await client.get(f"/auth/callback?code=abc&state={dash_state}", follow_redirects=False)
        assert back.status_code == 302 and back.headers["location"] == "/#/team"
    finally:
        services.set_oauth_transport(None)


async def test_render_route_is_internal_and_token_checked(client, tmp_data_dir, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_data_dir))
    denied = await client.get("/render/abc123?static=1")
    assert denied.status_code == 403
    token = render_token("abc123")
    wrong = await client.get(f"/render/other?render_token={token}")
    assert wrong.status_code == 403
    ok = await client.get(f"/render/abc123?static=1&render_token={token}")
    assert ok.status_code in (200, 503)  # 503 until the web UI is built


async def test_image_route_serves_only_hex_names(client, tmp_data_dir, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_data_dir))
    assert (await client.get("/img/../../etc/passwd")).status_code in (404, 400)
    assert (await client.get("/img/" + "a" * 32 + ".png")).status_code == 404


async def test_readyz_reports_worker_heartbeat(client):
    from sqlalchemy import text

    down = await client.get("/readyz")
    assert down.status_code == 503
    async with session_scope() as session:
        await session.execute(text("INSERT INTO worker_heartbeat (worker_id, beat_at) VALUES ('w', now())"))
    up = await client.get("/readyz")
    assert up.status_code == 200 and up.json()["worker"] == "ok"
    assert (await client.get("/healthz")).json() == {"ok": True}


async def test_security_headers_and_request_id(client):
    response = await client.get("/healthz")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert "style-src 'self' 'unsafe-inline'" in response.headers["content-security-policy"]
    assert response.headers["x-request-id"]
