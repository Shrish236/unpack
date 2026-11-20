"""Reconciler (§3.2–3.4) and comment publishing (§3.5, §8.3, §8.4) against a mocked GitHub."""

from __future__ import annotations


import pytest
from PIL import Image
from sqlalchemy import select

from server.app.db import session_scope
from server.app.jobs import handlers, render as render_mod
from server.app.jobs.reconciler import Target, decide, reconcile_once
from server.app.models import PullRequest, Render, TrackedBranch

from .conftest import Origin, drain_jobs
from .helpers import create_repo, gzip_json, ingest_headers, origin_payload, standard_files


@pytest.fixture
def origin(tmp_path):
    base, head = standard_files()
    return Origin(tmp_path, base, head)


@pytest.fixture
def no_render(monkeypatch):
    async def fail(public_id, file_name):
        raise render_mod.RenderFailed("browser disabled in tests")

    monkeypatch.setattr(handlers, "render_with_retry", fail)


def pr_for(origin, head_sha: str | None = None, number: int = 7) -> dict:
    return {"number": number, "title": "Add retries", "html_url": f"https://github.com/o/r/pull/{number}",
            "head": {"sha": head_sha or origin.head_sha, "ref": "feature/x"}, "base": {"ref": "main"}}


async def ingest(client, token, origin):
    response = await client.post("/v1/ingest", content=gzip_json(origin_payload(origin)),
                                 headers=ingest_headers(token))
    assert response.status_code == 202, response.text
    return response.json()["analysis"]["public_id"]




async def test_pr_gets_one_comment_then_stays_unchanged(client, tmp_data_dir, origin, fake_github, no_render):
    _, token = await create_repo(remote_url=origin.remote_url)
    public_id = await ingest(client, token, origin)
    await drain_jobs()
    fake_github.open_prs = [pr_for(origin)]

    assert await reconcile_once() == 1
    await drain_jobs()
    assert len(fake_github.created) == 1
    body = fake_github.created[0]["body"]
    assert body.startswith(f"<!-- unpack:v1 analysis={public_id} -->")
    assert f"https://unpack.test/a/{public_id}" in body
    assert "Functions changed" in body
    assert "Not reached by any test" in body and "brand_new" in body
    assert "Reasons unavailable" not in body  # the banner is only shown when the analysis has one
    assert "No agent session was sent" in body  # banner for a push without a session

    async with session_scope() as session:
        pr = (await session.execute(select(PullRequest))).scalar_one()
        assert pr.comment_id == fake_github.created[0]["id"]
        assert pr.last_published_analysis_id is not None

    await reconcile_once()
    await drain_jobs()
    assert len(fake_github.created) == 1 and fake_github.updated == []  # nothing changed, nothing written


async def test_existing_marker_comment_is_updated_not_duplicated(client, tmp_data_dir, origin, fake_github, no_render):
    _, token = await create_repo(remote_url=origin.remote_url)
    await ingest(client, token, origin)
    await drain_jobs()
    fake_github.open_prs = [pr_for(origin)]
    fake_github.comments[555] = {"id": 555, "body": "<!-- unpack:v1 analysis=old -->\nold text"}
    await reconcile_once()
    await drain_jobs()
    assert fake_github.created == []
    assert len(fake_github.updated) == 1 and fake_github.updated[0]["id"] == 555


async def test_pr_behind_latest_gets_partial_coverage_banner(client, tmp_data_dir, origin, fake_github, no_render):
    _, token = await create_repo(remote_url=origin.remote_url)
    await ingest(client, token, origin)
    await drain_jobs()
    older = origin.base_sha  # the PR head is an older commit that GitHub has, not the analysed push
    fake_github.open_prs = [pr_for(origin, head_sha=older)]
    fake_github.compare_status[origin.head_sha] = {"status": "behind", "ahead_by": 0, "behind_by": 2}
    await reconcile_once()
    await drain_jobs()
    assert len(fake_github.created) == 1
    assert "Covers up to" in fake_github.created[0]["body"]
    assert "2 newer commits were not analysed" in fake_github.created[0]["body"]


async def test_pr_head_not_yet_on_github_waits(client, tmp_data_dir, origin, fake_github, no_render):
    _, token = await create_repo(remote_url=origin.remote_url)
    await ingest(client, token, origin)
    await drain_jobs()
    fake_github.open_prs = [pr_for(origin, head_sha=origin.base_sha)]
    fake_github.compare_status[origin.head_sha] = {"status": "ahead", "ahead_by": 1, "behind_by": 0}
    await reconcile_once()
    await drain_jobs()
    assert fake_github.created == []  # our push is ahead of GitHub's PR head: wait, do not publish a guess
    async with session_scope() as session:
        tracked = (await session.execute(select(TrackedBranch))).scalar_one()
        assert tracked.status == "linked"
        assert tracked.needs_publish is True  # still pending: the poller keeps checking


async def test_diverged_branch_is_marked_out_of_date(client, tmp_data_dir, origin, fake_github, no_render):
    _, token = await create_repo(remote_url=origin.remote_url)
    await ingest(client, token, origin)
    await drain_jobs()
    fake_github.open_prs = [pr_for(origin, head_sha=origin.base_sha)]
    fake_github.compare_status[origin.head_sha] = {"status": "diverged", "ahead_by": 1, "behind_by": 1}
    await reconcile_once()
    await drain_jobs()
    assert len(fake_github.created) == 1
    assert "Out of date" in fake_github.created[0]["body"]


async def test_no_pr_means_waiting_with_backoff(client, tmp_data_dir, origin, fake_github, no_render):
    _, token = await create_repo(remote_url=origin.remote_url)
    await ingest(client, token, origin)
    await drain_jobs()
    fake_github.open_prs = []
    await reconcile_once()
    async with session_scope() as session:
        tracked = (await session.execute(select(TrackedBranch))).scalar_one()
        assert tracked.status == "waiting_for_pr"
        assert tracked.needs_publish is True  # the poller keeps looking for the PR
    assert fake_github.created == []


async def test_render_finished_later_adds_image_on_next_publish(client, tmp_data_dir, origin, fake_github, monkeypatch):
    async def fake_render(public_id, file_name):
        path = render_mod.images_dir() / f"{file_name}.png"
        img = Image.effect_noise((1200, 700), 80).convert("RGB")
        img.save(path, format="PNG")
        return path

    monkeypatch.setattr(handlers, "render_with_retry", fake_render)
    _, token = await create_repo(remote_url=origin.remote_url)
    await ingest(client, token, origin)
    await drain_jobs()  # analysis, then render_image
    fake_github.open_prs = [pr_for(origin)]
    await reconcile_once()
    await drain_jobs()
    assert len(fake_github.created) == 1
    body = fake_github.created[0]["body"]
    image_url = body.split("](")[1].split(")")[0]  # the image link in the comment
    assert image_url.startswith("https://unpack.test/img/") and image_url.endswith(".png")
    served = await client.get(image_url.replace("https://unpack.test", ""))
    assert served.status_code == 200 and served.headers["content-type"] == "image/png"
    assert "immutable" in served.headers["cache-control"]
    async with session_scope() as session:
        render = (await session.execute(select(Render))).scalar_one()
        assert render.status == "done" and len(render.file_name) == 32


async def test_failed_analysis_publishes_a_short_failure_comment(client, tmp_data_dir, origin, fake_github, no_render):
    _, token = await create_repo(remote_url=origin.remote_url)
    payload = origin_payload(origin, with_head_content=False)  # head unknown to origin: analysis fails
    response = await client.post("/v1/ingest", content=gzip_json(payload), headers=ingest_headers(token))
    assert response.status_code == 202
    await drain_jobs()
    fake_github.open_prs = [pr_for(origin)]
    await reconcile_once()
    await drain_jobs()
    assert len(fake_github.created) == 1
    assert "could not be completed (graph_unavailable)" in fake_github.created[0]["body"]


async def test_skips_repos_without_the_app(client, tmp_data_dir, origin, fake_github, no_render):
    _, token = await create_repo(remote_url=origin.remote_url, installation_id=None, status="active")
    # An active repo without an installation can still ingest, but nothing may be published to GitHub.
    response = await client.post("/v1/ingest", content=gzip_json(origin_payload(origin)), headers=ingest_headers(token))
    assert response.status_code == 202
    await drain_jobs()
    fake_github.open_prs = [pr_for(origin)]
    await reconcile_once()
    await drain_jobs()
    assert fake_github.created == []


def test_decision_rules():
    class A:  # a stand-in analysis row
        id = 5
        status = "done"

    head = "a" * 40
    common = dict(latest_id=5, latest_status="done", latest_head=head, done_by_head={}, latest_short="aaaaaaa")
    assert decide(decision={"status": "identical"}, pr_head=head, age_seconds=10, **common) == Target(5, "analysis")
    assert decide(decision={"status": "ahead", "ancestor": None}, pr_head="b" * 40, age_seconds=10, **common) == "wait"
    assert decide(decision={"status": "ahead", "ancestor": None}, pr_head="b" * 40, age_seconds=700, **common) is None
    anc = decide(decision={"status": "ahead", "ancestor": [9, "c" * 40]}, pr_head="b" * 40, age_seconds=700, **common)
    assert anc.analysis_id == 9 and anc.banner_override["message"].startswith("Covers up to ccccccc")
    assert decide(decision={"status": "diverged"}, pr_head="b" * 40, age_seconds=10, **common).mode == "out_of_date"
    behind = decide(decision={"status": "behind", "behind_by": 3}, pr_head="b" * 40, age_seconds=10, **common)
    assert behind.banner_override["message"].endswith("3 newer commits were not analysed.")
    older = decide(decision=None, pr_head="c" * 40, age_seconds=10,
                   **{**common, "done_by_head": {"c" * 40: 9}})
    assert older == Target(9, "analysis")
    waiting = decide(decision=None, pr_head=head, age_seconds=10,
                     **{**common, "latest_status": "running"})
    assert waiting == "wait"
