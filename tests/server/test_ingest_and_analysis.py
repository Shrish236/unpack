"""Ingest contract (§5.1) and the analysis of a push end to end (§6), with a real git origin."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from server.app.db import session_scope
from server.app.models import TrackedBranch
from server.app.security import encrypt_secret, new_session_id

from .conftest import Origin, drain_jobs
from .helpers import create_repo, gzip_json, ingest_headers, origin_payload, standard_files


async def post_ingest(client, token, obj):
    return await client.post("/v1/ingest", content=gzip_json(obj), headers=ingest_headers(token))


async def login(client, user_id: int = 1, github_id: int = 42, login_name: str = "octo") -> str:
    from datetime import datetime, timedelta, timezone

    from server.app.models import User, WebSession

    async with session_scope() as session:
        user = User(github_id=github_id, login=login_name, avatar_url=None)
        session.add(user)
        await session.flush()
        sid = new_session_id()
        session.add(WebSession(id=sid, user_id=user.id, oauth_token_encrypted=encrypt_secret("gho_viewer"),
                               expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
    client.cookies.set("unpack_session", sid)
    return sid


@pytest.fixture
def origin(tmp_path):
    base, head = standard_files()
    return Origin(tmp_path, base, head)


async def test_ingest_queues_analysis_and_tracks_branch(client, tmp_data_dir, origin):
    repo_id, token = await create_repo(remote_url=origin.remote_url)
    response = await post_ingest(client, token, origin_payload(origin))
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["analysis"]["status"] == "queued"
    assert body["analysis"]["url"].startswith("https://unpack.test/a/")
    assert body["tracking"] == {"branch": "feature/x", "status": "waiting_for_pr"}
    assert body["deduplicated"] is False
    async with session_scope() as session:
        tracked = (await session.execute(select(TrackedBranch))).scalar_one()
        assert tracked.latest_head_sha == origin.head_sha
        assert tracked.needs_publish is True


async def test_same_head_is_deduplicated(client, tmp_data_dir, origin):
    _, token = await create_repo(remote_url=origin.remote_url)
    first = await post_ingest(client, token, origin_payload(origin))
    second = await post_ingest(client, token, origin_payload(origin))
    assert second.status_code == 200
    assert second.json()["deduplicated"] is True
    assert second.json()["analysis"]["public_id"] == first.json()["analysis"]["public_id"]


async def test_ingest_error_codes(client, tmp_data_dir, origin, monkeypatch):
    from server.app.config import settings

    _, token = await create_repo(remote_url=origin.remote_url)
    good = origin_payload(origin)

    bad_token = await post_ingest(client, "unp_wrong", good)
    assert bad_token.status_code == 401 and bad_token.json()["error"]["code"] == "invalid_token"

    plain = await client.post("/v1/ingest", content=b"{}", headers={"Authorization": f"Bearer {token}",
                                                                   "Content-Type": "application/json"})
    assert plain.status_code == 415

    wrong_version = await post_ingest(client, token, {**good, "schema_version": 2})
    assert wrong_version.status_code == 422
    assert wrong_version.json()["error"]["details"] == {"supported": [1]}

    mismatch = await post_ingest(client, token, origin_payload(origin, owner="someone", name="else"))
    assert mismatch.status_code == 403 and mismatch.json()["error"]["code"] == "repo_mismatch"

    bad_sha = await post_ingest(client, token, {**good, "head_sha": "XYZ"})
    assert bad_sha.status_code == 400

    refs = await post_ingest(client, token, {**good, "branch": "refs/heads/x"})
    assert refs.status_code == 400

    monkeypatch.setattr(settings, "MAX_PAYLOAD_UNCOMPRESSED_BYTES", 100)
    big = await post_ingest(client, token, good)
    assert big.status_code == 413


async def test_app_missing_repo_is_disabled(client, tmp_data_dir, origin):
    _, token = await create_repo(remote_url=origin.remote_url, status="app_missing", installation_id=None)
    response = await post_ingest(client, token, origin_payload(origin))
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "repo_disabled"
    assert "install_url" in error["details"]


async def test_default_branch_is_analysed_but_not_tracked(client, tmp_data_dir, origin):
    _, token = await create_repo(remote_url=origin.remote_url)
    response = await post_ingest(client, token, origin_payload(origin, branch="main"))
    assert response.status_code == 202
    assert response.json()["tracking"]["status"] == "untracked"
    async with session_scope() as session:
        assert (await session.execute(select(TrackedBranch))).first() is None


async def test_analysis_facts_are_computed_from_code(client, tmp_data_dir, origin, fake_github):
    _, token = await create_repo(remote_url=origin.remote_url)
    response = await post_ingest(client, token, origin_payload(origin))
    public_id = response.json()["analysis"]["public_id"]
    assert await drain_jobs() >= 1

    await login(client)
    result = await client.get(f"/api/analyses/{public_id}")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["analysis"]["status"] == "done"
    assert body["analysis"]["head_sha"] == origin.head_sha

    stats = body["stats"]
    assert stats["functions_changed"] == 2
    assert stats["by_change"]["functional"] == 1  # helper: return value changed
    assert stats["by_change"]["added"] == 1  # brand_new
    assert stats["by_source"]["outside_session"] == 2
    assert stats["not_reached_by_tests"] == 1  # brand_new has no test

    nodes = {n["id"]: n for n in body["graph"]["nodes"]}
    assert nodes["pkg/core.py::helper"]["layer"] == "changed"
    assert nodes["pkg/core.py::helper"]["test"]["label"] in ("reached", "direct")
    assert nodes["pkg/core.py::brand_new"]["test"]["label"] == "none"
    assert nodes["pkg/core.py::compute"]["layer"] == "neighbor"
    # Client.send is two hops up from helper, so it is impact, shown in a collapsed group rather than as a node.
    collapsed_ids = {i for g in body["graph"]["collapsed"] for i in g["node_ids"]}
    impacted = {h["id"] for hops in body["impact"]["by_node"].values() for h in hops}
    assert "pkg/core.py::compute" in impacted and "pkg/core.py::Client.send" in impacted
    assert "pkg/core.py::Client.send" in collapsed_ids
    assert body["impact"]["summary"]["functions"] >= 2

    assert body["reading_order"].index("pkg/core.py::helper") < body["reading_order"].index("pkg/core.py::brand_new")
    assert body["banner"]["kind"] == "no_session"
    assert body["diff_hunks"]["pkg/core.py::helper"][0]["patch"].startswith("@@")
    assert body["reasons"] == {}
    assert body["findings"] == []


async def test_analysis_fails_cleanly_when_head_is_unknown(client, tmp_data_dir, origin, fake_github):
    _, token = await create_repo(remote_url=origin.remote_url)
    payload = origin_payload(origin, with_head_content=False)
    response = await post_ingest(client, token, payload)
    public_id = response.json()["analysis"]["public_id"]
    await drain_jobs()
    await login(client)
    body = (await client.get(f"/api/analyses/{public_id}")).json()
    assert body["analysis"]["status"] == "failed"
    assert body["analysis"]["error_code"] == "graph_unavailable"


async def test_analysis_uses_fetched_head_when_contents_were_too_large(client, tmp_data_dir, origin, fake_github):
    origin.push_head_to_origin()  # GitHub now has the head commit
    _, token = await create_repo(remote_url=origin.remote_url)
    response = await post_ingest(client, token, origin_payload(origin, with_head_content=False))
    public_id = response.json()["analysis"]["public_id"]
    await drain_jobs()
    await login(client)
    body = (await client.get(f"/api/analyses/{public_id}")).json()
    assert body["analysis"]["status"] == "done", body
    assert body["stats"]["functions_changed"] == 2


async def test_access_rules(client, tmp_data_dir, origin, fake_github):
    _, token = await create_repo(remote_url=origin.remote_url)
    public_id = (await post_ingest(client, token, origin_payload(origin))).json()["analysis"]["public_id"]

    anonymous = await client.get(f"/api/analyses/{public_id}")
    assert anonymous.status_code == 401 and anonymous.json()["error"]["code"] == "not_logged_in"

    await login(client)
    queued = await client.get(f"/api/analyses/{public_id}")
    assert queued.status_code == 200 and queued.headers["retry-after"] == "3"
    assert queued.json()["analysis"]["status"] == "queued"

    await drain_jobs()
    # The access check is cached for 10 minutes; expire it to model time passing.
    from sqlalchemy import delete

    from server.app.models import AccessCache

    async with session_scope() as session:
        await session.execute(delete(AccessCache))
    fake_github.viewer_access = 404
    denied = await client.get(f"/api/analyses/{public_id}")
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "no_repo_access"

    missing = await client.get("/api/analyses/doesnotexist")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"

    client.cookies.clear()
    anonymous_missing = await client.get("/api/analyses/doesnotexist")
    assert anonymous_missing.status_code == 401  # login is checked before lookup, so IDs do not leak
