"""Job handlers: analyze_push, render_image, build_graph (server design §6)."""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, text


from ..config import settings
from ..db import session_scope
from ..models import Analysis, Decision, FunctionReason, SessionSignals, LLMCall, Push, Render, Repo, ReviewFinding, Session
from ..pipeline.rollup import rollup_measured
from ..pipeline.analysis import AnalysisFailed, analyze_push
from ..pipeline.repos import CommitUnavailable, ensure_commit, ensure_mirror, save_cached_graph
from ..security import new_file_name
from ..services import get_github
from .queue import enqueue
from .render import RenderFailed, render_with_retry

log = logging.getLogger("unpack.jobs")


def read_payload(path: str) -> dict[str, Any]:
    with gzip.open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _installation_token(installation_id: int | None) -> str | None:
    if installation_id is None:
        return None
    return await get_github().installation_token(installation_id)


async def _mark_publish_pending(session: Any, repo_id: int, branch: str) -> None:
    """Something a post depends on changed; the poller will post on its next sweep."""
    await session.execute(
        text("UPDATE tracked_branches SET needs_publish = true WHERE repo_id = :r AND branch = :b"),
        {"r": repo_id, "b": branch},
    )


async def _daily_tokens_used(session: Any, repo_id: int) -> int:
    since = _now() - timedelta(hours=24)
    total = (
        await session.execute(
            select(func.coalesce(func.sum(LLMCall.input_tokens + LLMCall.output_tokens), 0))
            .join(Analysis, Analysis.id == LLMCall.analysis_id)
            .join(Push, Push.id == Analysis.push_id)
            .where(Push.repo_id == repo_id, LLMCall.created_at >= since)
        )
    ).scalar_one()
    return int(total or 0)


async def analyze_push_job(payload: dict[str, Any]) -> None:
    analysis_id = int(payload["analysis_id"])
    async with session_scope() as session:
        analysis = await session.get(Analysis, analysis_id)
        if analysis is None or analysis.status == "done":
            return
        push = await session.get(Push, analysis.push_id)
        repo = await session.get(Repo, push.repo_id)
        analysis.status = "running"
        analysis.started_at = _now()
        tokens_today = await _daily_tokens_used(session, repo.id)
        snapshot = {
            "repo_id": repo.id, "owner": repo.owner, "name": repo.name,
            "remote_url": repo.remote_url or f"https://github.com/{repo.owner}/{repo.name}.git",
            "installation_id": repo.installation_id, "payload_path": push.payload_path,
            "push_id": push.id, "branch": push.branch,
            "agent": (push.session_agent or None),
            "tokens_today": tokens_today,
        }

    token = await _installation_token(snapshot["installation_id"])
    data = await asyncio.to_thread(read_payload, snapshot["payload_path"])
    try:
        outcome = await analyze_push(
            repo_id=snapshot["repo_id"], owner=snapshot["owner"], name=snapshot["name"],
            remote_url=snapshot["remote_url"], token=token, payload=data,
            daily_tokens_used=snapshot["tokens_today"],
        )
    except AnalysisFailed as exc:
        await _store_failure(analysis_id, snapshot["push_id"], snapshot["repo_id"], snapshot["branch"],
                             exc.code, exc.message, exc.governance)
        if exc.governance is not None and exc.governance.signals:
            try:
                await rollup_measured()
            except Exception:
                log.exception("dashboard rollup failed")
        return

    async with session_scope() as session:
        analysis = await session.get(Analysis, analysis_id)
        # Insert findings FIRST and flush to obtain real DB IDs for graph_view & timeline links
        finding_rows: list[ReviewFinding] = []
        for finding in outcome.findings:
            row = ReviewFinding(
                analysis_id=analysis_id, kind=finding["kind"], finding=finding["finding"],
                functions=finding.get("functions", []), evidence=finding.get("evidence", []),
            )
            session.add(row)
            finding_rows.append(row)
        if finding_rows:
            await session.flush()

        # Populate node.finding_ids on graph_view using real ReviewFinding IDs
        finding_ids_by_node: dict[str, list[int]] = {}
        for row in finding_rows:
            for fid in row.functions or []:
                finding_ids_by_node.setdefault(fid, []).append(row.id)
        for node in outcome.graph_view.get("nodes", []):
            fids = finding_ids_by_node.get(node["id"])
            if fids:
                node["finding_ids"] = fids

        # Append claim timeline entries with their real DB finding_id
        timeline = list(outcome.timeline)
        turn_ts_map = {t["turn_id"]: t.get("ts", "") for t in outcome.session_turns}
        for turn_id, label, finding_idx in outcome.claim_turns:
            if 0 <= finding_idx < len(finding_rows):
                row = finding_rows[finding_idx]
                timeline.append(
                    {
                        "turn": turn_id,
                        "kind": "claim",
                        "ts": turn_ts_map.get(turn_id, ""),
                        "label": label,
                        "nodes": list(row.functions or []),
                        "reverted": False,
                        "exit_code": None,
                        "finding_id": row.id,
                    }
                )

        analysis.status = "done"
        analysis.error_code = None
        analysis.error_message = None
        analysis.summary = outcome.summary
        analysis.banner = outcome.banner
        analysis.stats = outcome.stats
        analysis.facts = outcome.facts
        analysis.graph_view = outcome.graph_view
        analysis.reading_order = outcome.reading_order
        analysis.impact = outcome.impact
        analysis.diff_hunks = outcome.diff_hunks
        analysis.diff_files = outcome.diff_files
        analysis.flow = outcome.flow
        analysis.timeline = timeline
        analysis.llm_model = outcome.llm_model
        analysis.rejected_count = outcome.rejected_count
        analysis.finished_at = _now()

        for node_id, reason in outcome.reasons.items():
            session.add(FunctionReason(
                analysis_id=analysis_id, node_id=node_id, reason=reason["reason"],
                driver=reason["driver"], history=reason.get("history", []),
                confidence=reason.get("confidence", "high"), evidence=reason.get("evidence", []),
                source=reason.get("source", "session"), rejected=reason.get("rejected"),
            ))
        if outcome.signals:
            _add_governance(session, analysis_id, outcome.signals, outcome.decisions, outcome.highlights, outcome.steering)
        analysis.prompt_version = settings.PROMPT_VERSION
        _add_llm_calls(session, analysis_id, outcome.llm_calls)
        if data.get("session") is not None:
            existing = (await session.execute(select(Session).where(Session.push_id == snapshot["push_id"]))).scalar_one_or_none()
            if existing is None:
                session.add(Session(push_id=snapshot["push_id"], agent=data["session"]["agent"],
                                    file_name=data["session"]["file_name"], turns=outcome.session_turns))
            else:
                existing.turns = outcome.session_turns
        if outcome.has_python_changes and outcome.changed_count > 0:
            await enqueue(session, "render_image", {"analysis_id": analysis_id},
                          dedupe_key=f"render:{analysis_id}")
        await _mark_publish_pending(session, snapshot["repo_id"], snapshot["branch"])

    if outcome.signals:
        try:
            await rollup_measured()
        except Exception:  # the dashboards are derived; a rollup problem must not fail the analysis
            log.exception("dashboard rollup failed")


def _add_llm_calls(session: Any, analysis_id: int, calls: list[Any]) -> None:
    for call in calls:
        session.add(LLMCall(
            analysis_id=analysis_id, purpose=call.purpose, model=call.model, attempt=call.attempt,
            prompt_version=call.prompt_version, input_tokens=call.input_tokens, output_tokens=call.output_tokens,
            thinking_tokens=call.thinking_tokens, latency_ms=call.latency_ms, status=call.status, error=call.error,
            finish_reason=call.finish_reason, request_hash=call.request_hash, response_text=call.response_text,
        ))


def _add_governance(session: Any, analysis_id: int, signals: dict[str, Any], decisions: list[dict[str, Any]],
                    highlights: list[dict[str, Any]], steering: dict[str, Any]) -> None:
    for d in decisions:
        session.add(Decision(
            analysis_id=analysis_id, turn=int(d["turn"][1:]), actor=d["actor"], kind=d["kind"], type=d["type"],
            proposal=d["proposal"], choice=d["choice"], statement=d.get("statement", ""), quote=d["quote"],
            rule_id=d.get("rule_id"), rule_followed=d.get("rule_followed"), source=d.get("source", "llm"),
            node_ids=d.get("nodes", []), outcome=d.get("outcome", "ok"),
        ))
    session.add(SessionSignals(analysis_id=analysis_id, signals=signals, highlights=highlights, steering=steering))


async def _store_failure(analysis_id: int, push_id: int, repo_id: int, branch: str, code: str, message: str,
                         gov: Any = None) -> None:
    async with session_scope() as session:
        analysis = await session.get(Analysis, analysis_id)
        analysis.status = "failed"
        analysis.error_code = code
        analysis.error_message = message[:1000]
        analysis.finished_at = _now()
        if gov is not None and gov.signals:  # the graph failed, but the session's metrics are still worth keeping
            _add_governance(session, analysis_id, gov.signals, gov.decisions, gov.highlights, gov.steering)
        if gov is not None:  # tokens spent on a push that then failed still count against the daily budget
            _add_llm_calls(session, analysis_id, gov.llm_calls)
        await _mark_publish_pending(session, repo_id, branch)


async def mark_failed_after_retries(payload: dict[str, Any], error: str) -> None:
    """Called by the worker when a job runs out of attempts."""
    if payload.get("analysis_id") is None:
        return
    async with session_scope() as session:
        analysis = await session.get(Analysis, int(payload["analysis_id"]))
        if analysis is not None and analysis.status != "done":
            analysis.status = "failed"
            analysis.error_code = "internal_error"
            analysis.error_message = error[:1000]
            analysis.finished_at = _now()


async def render_image_job(payload: dict[str, Any]) -> None:
    analysis_id = int(payload["analysis_id"])
    async with session_scope() as session:
        analysis = await session.get(Analysis, analysis_id)
        if analysis is None or analysis.status != "done":
            return
        done = (await session.execute(
            select(Render).where(Render.analysis_id == analysis_id, Render.status == "done")
        )).first()
        if done:
            return
        render = Render(analysis_id=analysis_id, file_name=new_file_name(), status="queued")
        session.add(render)
        await session.flush()
        public_id = analysis.public_id
        render_id = render.id
        file_name = render.file_name
        push = await session.get(Push, analysis.push_id)
        repo_id, branch = push.repo_id, push.branch

    try:
        path = await render_with_retry(public_id, file_name)
        size = path.stat().st_size
        status, error = "done", None
    except RenderFailed as exc:
        size, status, error = 0, "failed", str(exc)[:500]
        log.info("render failed for analysis %s: %s", analysis_id, error)

    async with session_scope() as session:
        render = await session.get(Render, render_id)
        render.status = status
        render.bytes = size
        render.error = error
        await _mark_publish_pending(session, repo_id, branch)


async def ensure_head_graph(repo_id: int, owner: str, name: str, remote_url: str, token: str | None, sha: str) -> Any:
    """Whole-repo head graph for one commit: the cache first, a full build only when cold."""
    from ..pipeline.build import full_graph_for
    from ..pipeline.repos import load_cached_graph

    cached = await asyncio.to_thread(load_cached_graph, repo_id, sha)
    if cached is not None:
        return cached
    mirror = await ensure_mirror(owner, name, remote_url, token)
    try:
        await ensure_commit(mirror, sha, token)
    except CommitUnavailable as exc:
        raise AnalysisFailed("graph_unavailable", str(exc)) from exc
    return await asyncio.to_thread(full_graph_for, repo_id, str(mirror), sha)


async def build_graph_job(payload: dict[str, Any]) -> None:
    repo_id = int(payload["repo_id"])
    async with session_scope() as session:
        repo = await session.get(Repo, repo_id)
        if repo is None:
            return
        owner, name = repo.owner, repo.name
        remote_url = repo.remote_url or f"https://github.com/{owner}/{name}.git"
        installation_id = repo.installation_id
    token = await _installation_token(installation_id)
    graph = await ensure_head_graph(repo_id, owner, name, remote_url, token, payload["sha"])

    await asyncio.to_thread(save_cached_graph, repo_id, payload["sha"], graph)
    async with session_scope() as session:
        repo = await session.get(Repo, repo_id)
        repo.graph_built_sha = payload["sha"]


async def dispatch(job_type: str, payload: dict[str, Any]) -> Any:
    from .publish import publish_job

    if job_type == "analyze_push":
        return await analyze_push_job(payload)
    if job_type == "render_image":
        return await render_image_job(payload)
    if job_type == "publish_comment":
        return await publish_job(payload)
    if job_type == "build_graph":
        return await build_graph_job(payload)
    raise ValueError(f"unknown job type {job_type}")

