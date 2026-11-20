"""The poller that replaces webhooks: defaults, the PR hold window, conditional PR lists, cached compares,
and the Unpack section at the top of the PR description."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from server.app.config import Settings, settings
from server.app.db import session_scope
from server.app.github import description
from server.app.jobs import handlers
from server.app.jobs.reconciler import reconcile_once
from server.app.jobs.render import RenderFailed
from server.app.models import Push, TrackedBranch

from .conftest import Origin, drain_jobs
from .helpers import create_repo, gzip_json, ingest_headers, origin_payload, standard_files
from .test_publish_and_reconcile import pr_for


@pytest.fixture
def origin(tmp_path):
    base, head = standard_files()
    return Origin(tmp_path, base, head)


@pytest.fixture
def no_render(monkeypatch):
    async def fail(public_id, file_name):
        raise RenderFailed("browser disabled in tests")

    monkeypatch.setattr(handlers, "render_with_retry", fail)


async def ingest(client, token, origin):
    response = await client.post("/v1/ingest", content=gzip_json(origin_payload(origin)),
                                 headers=ingest_headers(token))
    assert response.status_code == 202, response.text


async def age_latest_push(days: float) -> None:
    async with session_scope() as session:
        push = (await session.execute(select(Push))).scalars().one()
        push.received_at = datetime.now(timezone.utc) - timedelta(days=days)


def test_poller_defaults_match_the_decisions():
    assert Settings.model_fields["RECONCILE_INTERVAL_SECONDS"].default == 10
    assert Settings.model_fields["PR_WAIT_DAYS"].default == 3
    assert Settings.model_fields["PR_DESCRIPTION_SECTION"].default is True
    assert Settings.model_fields["INSTALLATION_SYNC_SECONDS"].default == 900
    assert "GITHUB_WEBHOOK_SECRET" not in Settings.model_fields
    assert "TRACK_MAX_DAYS" not in Settings.model_fields


async def test_webhook_endpoint_is_gone(client):
    response = await client.post("/github/webhook", content=b"{}", headers={"X-GitHub-Event": "ping"})
    assert response.status_code == 404


async def test_branch_is_held_for_three_days_without_a_pr(client, tmp_data_dir, origin, fake_github, no_render):
    _, token = await create_repo(remote_url=origin.remote_url)
    await ingest(client, token, origin)
    await drain_jobs()
    fake_github.open_prs = []

    await age_latest_push(2)
    await reconcile_once()
    async with session_scope() as session:
        assert (await session.execute(select(TrackedBranch))).scalar_one().status == "waiting_for_pr"

    await age_latest_push(3.5)
    await reconcile_once()
    async with session_scope() as session:
        tracked = (await session.execute(select(TrackedBranch))).scalar_one()
        assert tracked.status == "abandoned" and tracked.needs_publish is False


async def test_hold_window_is_configurable(client, tmp_data_dir, origin, fake_github, no_render, monkeypatch):
    monkeypatch.setattr(settings, "PR_WAIT_DAYS", 1)
    _, token = await create_repo(remote_url=origin.remote_url)
    await ingest(client, token, origin)
    await drain_jobs()
    fake_github.open_prs = []
    await age_latest_push(1.5)
    await reconcile_once()
    async with session_scope() as session:
        assert (await session.execute(select(TrackedBranch))).scalar_one().status == "abandoned"


async def test_unchanged_pull_list_is_a_304_and_posts_nothing_new(client, tmp_data_dir, origin, fake_github, no_render):
    _, token = await create_repo(remote_url=origin.remote_url)
    await ingest(client, token, origin)
    await drain_jobs()
    fake_github.open_prs = [pr_for(origin)]
    await reconcile_once()
    await drain_jobs()
    assert len(fake_github.created) == 1

    before = fake_github.not_modified
    await reconcile_once()
    await drain_jobs()
    assert fake_github.not_modified == before + 1  # the second list came back as 304
    assert len(fake_github.created) == 1 and fake_github.updated == []


async def test_compare_result_is_cached_between_sweeps(client, tmp_data_dir, origin, fake_github, no_render):
    _, token = await create_repo(remote_url=origin.remote_url)
    await ingest(client, token, origin)
    await drain_jobs()
    fake_github.open_prs = [pr_for(origin, head_sha=origin.base_sha)]
    fake_github.compare_status[origin.head_sha] = {"status": "behind", "ahead_by": 0, "behind_by": 2}
    await reconcile_once()
    await drain_jobs()
    await reconcile_once()
    await drain_jobs()
    compares = [c for c in fake_github.calls if c[1].count("/compare/") and c[0] == "GET"]
    assert len(compares) == 1


async def test_description_gets_the_unpack_section_at_the_top_and_keeps_the_authors_text(
        client, tmp_data_dir, origin, fake_github, no_render):
    _, token = await create_repo(remote_url=origin.remote_url)
    await ingest(client, token, origin)
    await drain_jobs()
    fake_github.open_prs = [pr_for(origin)]
    fake_github.pr_state[7] = {"state": "open", "body": "Adds retries to the client.\n\nSee issue 3."}
    await reconcile_once()
    await drain_jobs()
    assert fake_github.description_writes, "the description was not written"
    written = fake_github.description_writes[-1]
    assert written.startswith(description.BEGIN)
    assert written.index(description.END) < written.index("Adds retries to the client.")
    assert written.endswith("See issue 3.")
    assert fake_github.created[0]["body"] in written  # the same content as the comment

    before = len(fake_github.description_writes)
    await reconcile_once()
    await drain_jobs()
    assert len(fake_github.description_writes) == before  # unchanged: no second write


def test_description_merge_puts_the_section_first_and_replaces_it_in_place():
    section = description.section_for("v1")
    assert description.merge("", section) == section
    assert description.merge("Author text", section) == f"{section}\n\nAuthor text"
    old = f"{description.section_for('v1')}\n\nAuthor text"
    replaced = description.merge(old, description.section_for("v2"))
    assert replaced == f"{description.section_for('v2')}\n\nAuthor text"
    assert replaced.count(description.BEGIN) == 1


async def test_failing_installation_sync_backs_off_instead_of_retrying_every_sweep(monkeypatch):
    from server.app.jobs import reconciler

    calls = []

    async def failing():
        calls.append(1)
        raise RuntimeError("github down")

    monkeypatch.setattr(reconciler, "sync_installations", failing)
    monkeypatch.setattr(reconciler, "_last_installation_sync", None)
    await reconciler._maybe_sync_installations()
    await reconciler._maybe_sync_installations()  # the very next sweep must not call GitHub again
    assert len(calls) == 1


async def test_setup_page_answers_503_when_github_is_unreachable(client, tmp_data_dir, monkeypatch):
    from server.app.github import prs as gh_prs
    from server.app.github.service import GitHubError

    async def unreachable(svc, installation_id):
        raise GitHubError(500, "boom")

    monkeypatch.setattr(gh_prs, "installation_repositories", unreachable)
    response = await client.get("/github/setup?installation_id=1")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "unavailable"


async def test_first_installation_sync_runs_even_on_a_young_host(monkeypatch):
    """monotonic() counts from boot: a fresh process must sync once immediately, whatever the clock says."""
    from server.app.jobs import reconciler

    calls = []

    async def ok():
        calls.append(1)

    monkeypatch.setattr(reconciler, "sync_installations", ok)
    monkeypatch.setattr(reconciler, "_last_installation_sync", None)
    monkeypatch.setattr(reconciler.time, "monotonic", lambda: 5.0)  # a host that booted 5 seconds ago
    await reconciler._maybe_sync_installations()
    assert calls == [1]
