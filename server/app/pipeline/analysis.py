"""Analysis of one push: facts from the code, reasoning as a placeholder (server design §6)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from unpack_graph.diff import detect_changes
from unpack_graph.graph import build_graph
from unpack_graph.source import GitSource

from ..config import settings
from ..llm.placeholder import generate_reasons
from .graph_view import GraphBuild, InvalidGraphView, build_graph_view, validate_graph_view
from .payload import PayloadSource, build_overlay, changed_python_files, needs_head_fetch, parse_diff_hunks
from .repos import CommitUnavailable, ensure_commit, ensure_mirror, save_cached_graph


class AnalysisFailed(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class AnalysisOutcome:
    summary: str
    banner: dict[str, str] | None
    stats: dict[str, Any]
    facts: dict[str, Any]
    graph_view: dict[str, Any]
    reading_order: list[str]
    impact: dict[str, Any]
    diff_hunks: dict[str, list[dict[str, Any]]]
    timeline: list[dict[str, Any]]
    reasons: dict[str, dict[str, Any]]
    findings: list[dict[str, Any]]
    not_reached: list[str]
    changed_count: int
    has_python_changes: bool
    llm_model: str | None = None
    rejected_count: int = 0
    file_count: int = 0
    head_graph_cached: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def _summary(build: GraphBuild, file_count: int) -> str:
    n = build.stats["functions_changed"]
    if n == 0:
        return "No Python functions changed."
    untested = build.stats["not_reached_by_tests"]
    files = f"{file_count} file" + ("" if file_count == 1 else "s")
    tail = f"; {untested} not reached by any test" if untested else "; all reached by a test"
    return f"{n} function{'s' if n != 1 else ''} changed in {files}{tail}."


def _banner(payload: dict[str, Any], changed_count: int) -> dict[str, str] | None:
    if changed_count == 0:
        return None
    if payload.get("session") is None:
        return {"kind": "no_session",
                "message": "No agent session was sent for this push. Every change is listed as outside the session."}
    return {"kind": "reasons_unavailable", "message": "Reasons are not generated in this build yet."}


def _blocking_analysis(
    mirror_path: Any,
    base_sha: str,
    head_sha: str,
    head_source: Any,
    base_source: GitSource,
    diff_text: str,
    repo_id: int,
) -> tuple[GraphBuild, Any]:
    base_graph = build_graph(base_source, reach=False)
    head_graph = build_graph(head_source, reach=True)
    cs = detect_changes(mirror_path, base_sha, head_sha, base_graph=base_graph, head_graph=head_graph)
    hunks = parse_diff_hunks(diff_text)
    build = build_graph_view(cs, base_graph, head_graph, hunks)
    try:
        validate_graph_view(build, settings.MAX_GRAPH_NODES, settings.MAX_GRAPH_EDGES)
    except InvalidGraphView as exc:
        raise AnalysisFailed("invalid_graph_view", str(exc)) from exc
    save_cached_graph(repo_id, head_sha, head_graph)
    return build, head_graph


async def analyze_push(
    *,
    repo_id: int,
    owner: str,
    name: str,
    remote_url: str,
    token: str | None,
    payload: dict[str, Any],
) -> AnalysisOutcome:
    base_sha = payload["base_sha"]
    head_sha = payload["head_sha"]
    changed_files = payload.get("changed_files", [])

    try:
        mirror = await ensure_mirror(owner, name, remote_url, token)
    except Exception as exc:  # git clone failed
        raise AnalysisFailed("graph_unavailable", f"could not clone the repository: {exc}") from exc
    try:
        await ensure_commit(mirror, base_sha, token)
    except CommitUnavailable as exc:
        raise AnalysisFailed("graph_unavailable", f"base commit unavailable: {exc}") from exc

    base_source = GitSource(mirror, base_sha)
    if needs_head_fetch(changed_files):
        try:
            await ensure_commit(mirror, head_sha, token)
        except CommitUnavailable as exc:
            raise AnalysisFailed(
                "graph_unavailable",
                "a changed file was too large to send and the head commit is not on GitHub yet",
            ) from exc
        head_source: Any = GitSource(mirror, head_sha)
    else:
        overlay, removed = build_overlay(changed_files)
        head_source = PayloadSource(base_source, overlay, removed)

    try:
        build, head_graph = await asyncio.to_thread(
            _blocking_analysis, mirror, base_sha, head_sha, head_source, base_source,
            payload.get("diff", ""), repo_id,
        )
    except AnalysisFailed:
        raise
    except Exception as exc:
        raise AnalysisFailed("graph_failed", f"code graph build failed: {type(exc).__name__}") from exc

    changed_count = build.stats["functions_changed"]
    file_count = len({n["path"] for n in build.graph["nodes"] if n["layer"] in ("changed", "ghost")})
    has_session = payload.get("session") is not None
    reasoning = generate_reasons(build.changed_ids, has_session)

    return AnalysisOutcome(
        summary=reasoning.summary or _summary(build, file_count),
        banner=_banner(payload, changed_count),
        stats=build.stats,
        facts={"last_test_run": None, "tested_after_final_edit": False},
        graph_view=build.graph,
        reading_order=build.reading_order,
        impact=build.impact,
        diff_hunks=build.diff_hunks,
        timeline=reasoning.timeline,
        reasons=reasoning.reasons,
        findings=reasoning.findings,
        not_reached=build.not_reached,
        changed_count=changed_count,
        has_python_changes=bool(changed_python_files(changed_files)),
        llm_model=reasoning.model,
        rejected_count=reasoning.rejected_count,
        file_count=file_count,
        head_graph_cached=True,
    )
