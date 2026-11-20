"""Node details, codebase map, node edges, commit picker and turns (§5.5, §5.6)."""

from __future__ import annotations

import urllib.parse

import pytest

from .conftest import Origin, drain_jobs
from .helpers import create_repo, origin_payload, standard_files
from .test_ingest_and_analysis import login, post_ingest


@pytest.fixture
def origin(tmp_path):
    base, head = standard_files()
    return Origin(tmp_path, base, head)


async def analysed(client, origin, fake_github, tmp_data_dir):
    _, token = await create_repo(remote_url=origin.remote_url)
    public_id = (await post_ingest(client, token, origin_payload(origin))).json()["analysis"]["public_id"]
    await drain_jobs()
    await login(client)
    return public_id


async def test_node_detail_for_changed_function(client, tmp_data_dir, origin, fake_github):
    public_id = await analysed(client, origin, fake_github, tmp_data_dir)
    node_id = urllib.parse.quote("pkg/core.py::helper", safe="")
    response = await client.get(f"/api/analyses/{public_id}/nodes/{node_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["node"]["id"] == "pkg/core.py::helper"
    assert body["node"]["kind"] == "function"
    assert body["change"] == {"kind": "functional", "source": "outside_session"}
    assert "return x + 10" in body["source_head"]
    assert any(c["id"] == "pkg/core.py::compute" for c in body["callers"])
    assert body["tests"]["label"] in ("reached", "direct")
    assert body["tests"]["paths"] and body["tests"]["paths"][0][0].endswith("test_compute")
    assert body["diff"] and body["diff"][0]["patch"].startswith("@@")


async def test_node_detail_for_method_and_file_and_unknown(client, tmp_data_dir, origin, fake_github):
    public_id = await analysed(client, origin, fake_github, tmp_data_dir)
    method = urllib.parse.quote("pkg/core.py::Client.send", safe="")
    body = (await client.get(f"/api/analyses/{public_id}/nodes/{method}")).json()
    assert body["node"]["kind"] == "method"
    assert body["node"]["class"]["id"] == "pkg/core.py::Client"

    file_node = urllib.parse.quote("pkg/core.py", safe="")
    body = (await client.get(f"/api/analyses/{public_id}/nodes/{file_node}")).json()
    assert body["node"]["kind"] == "file"

    unknown = await client.get(f"/api/analyses/{public_id}/nodes/nope.py::zzz")
    assert unknown.status_code == 404


async def test_map_is_cached_and_supports_etag(client, tmp_data_dir, origin, fake_github):
    _, token = await create_repo(remote_url=origin.remote_url)
    await post_ingest(client, token, origin_payload(origin))
    await drain_jobs()
    await login(client)
    url = f"/api/repos/o/r/map?sha={origin.head_sha}"
    first = await client.get(url)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["map_sha"] == origin.head_sha
    assert body["columns"] == ["id", "kind", "parent", "loc", "fan_in", "is_test"]
    kinds = {row[0]: row[1] for row in body["nodes"]}
    assert kinds["pkg"] == "folder"
    assert kinds["pkg/core.py"] == "file"
    assert kinds["pkg/core.py::helper"] == "function"
    assert kinds["pkg/core.py::Client.send"] == "method"
    assert kinds["tests/test_core.py::test_compute"] == "test"
    assert body["counts"]["tests"] == 1
    assert first.headers["etag"] == f'"{origin.head_sha}"'
    assert "max-age=86400" in first.headers["cache-control"]

    cached = await client.get(url, headers={"If-None-Match": f'"{origin.head_sha}"'})
    assert cached.status_code == 304


async def test_node_edges(client, tmp_data_dir, origin, fake_github):
    _, token = await create_repo(remote_url=origin.remote_url)
    await post_ingest(client, token, origin_payload(origin))
    await drain_jobs()
    await login(client)
    response = await client.get(f"/api/repos/o/r/nodes/pkg/core.py::helper/edges?sha={origin.head_sha}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert [c["id"] for c in body["callers"]] == ["pkg/core.py::compute"]
    assert body["callers_total"] == 1


async def test_commit_picker_lists_analyses_for_the_pr(client, tmp_data_dir, origin, fake_github, monkeypatch):
    from server.app.jobs import handlers
    from server.app.jobs.reconciler import reconcile_once
    from server.app.jobs.render import RenderFailed

    from .test_publish_and_reconcile import pr_for

    async def no_browser(public_id, file_name):
        raise RenderFailed("disabled in tests")

    monkeypatch.setattr(handlers, "render_with_retry", no_browser)
    _, token = await create_repo(remote_url=origin.remote_url)
    await post_ingest(client, token, origin_payload(origin))
    await drain_jobs()
    fake_github.open_prs = [pr_for(origin)]
    await reconcile_once()
    await drain_jobs()
    await login(client)
    response = await client.get("/api/prs/o/r/7/analyses")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pull_request"]["number"] == 7
    assert body["analyses"][0]["short_sha"] == origin.head_sha[:7]
    assert body["analyses"][0]["commit_message"] == "change"
    assert body["analyses"][0]["is_published"] is True
    missing = await client.get("/api/prs/o/r/99/analyses")
    assert missing.status_code == 404


async def test_turns_validate_ids(client, tmp_data_dir, origin, fake_github):
    public_id = await analysed(client, origin, fake_github, tmp_data_dir)
    empty = await client.get(f"/api/analyses/{public_id}/turns?ids=")
    assert empty.status_code == 400 and empty.json()["error"]["code"] == "invalid_ids"
    too_many = await client.get(f"/api/analyses/{public_id}/turns?ids=" + ",".join(f"T{i}" for i in range(51)))
    assert too_many.status_code == 400
    ok = await client.get(f"/api/analyses/{public_id}/turns?ids=T1,T2")
    assert ok.status_code == 200 and ok.json() == {"turns": []}
