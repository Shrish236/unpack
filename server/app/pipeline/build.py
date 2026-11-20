"""CPU-bound graph work for one push. Runs in a worker process when ANALYSIS_PROCESSES > 0.

The base graph is cached per base commit (every push on a branch shares it). The head graph is
updated incrementally from the base with the library's update_graph, which re-extracts only the
changed files and re-resolves only the affected ones. Tests check it equals a full rebuild.
"""

from __future__ import annotations

import asyncio
import functools
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Any

from unpack_graph.graph import build_graph
from unpack_graph.incremental import update_graph
from unpack_graph.source import GitSource

from ..config import settings
from .changes import FuncChange, compute_changes
from .edit_linker import LinkOutcome, link_session_to_changes
from .graph_view import GraphBuild, InvalidGraphView, build_graph_view, validate_graph_view
from .payload import PayloadSource, parse_diff_hunks
from .agy_session import AGY_AGENT, parse_agy_transcript, reconstruct_edit_states
from .session import UnpackSession, parse_gemini_session
from .repos import load_cached_graph, save_cached_graph


class BuildFailed(Exception):
    """Carries an analysis error code back from the worker process."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def base_graph(repo_id: int, mirror: str, base_sha: str, base_source: GitSource | None = None) -> Any:
    cached = load_cached_graph(repo_id, base_sha, "base")
    if cached is not None:
        return cached
    graph = build_graph(base_source or GitSource(mirror, base_sha), reach=False)
    save_cached_graph(repo_id, base_sha, graph, "base")
    return graph


@dataclass
class AnalysisBuild:
    """Everything one analysis needs from the CPU-bound stage. Picklable, so it can come back from a worker process."""

    build: GraphBuild
    timings: dict[str, float]
    changes: list[FuncChange]
    unpack_session: UnpackSession | None
    link_outcome: LinkOutcome | None


def analyze_blocking(
    *,
    repo_id: int,
    mirror: str,
    base_sha: str,
    head_sha: str,
    overlay: dict[str, bytes],
    removed: list[str],
    diff_text: str,
    full_head: bool,
    changed_files: list[dict[str, Any]] | None = None,
    session_payload: dict[str, Any] | None = None,
) -> AnalysisBuild:
    """Graph facts for one push, plus the session parse and edit links when a session was sent.

    A pure function of its arguments, so it can run in a worker process.
    """
    import time

    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    base_src = GitSource(mirror, base_sha)
    base = base_graph(repo_id, mirror, base_sha, base_src)
    timings["base_s"] = time.perf_counter() - t0

    t1 = time.perf_counter()
    if full_head:
        head = build_graph(GitSource(mirror, head_sha), reach=True)
    else:
        source = PayloadSource(base_src, overlay, set(removed))
        head, _stats = update_graph(base, source, set(overlay), set(removed))
    timings["head_s"] = time.perf_counter() - t1
    save_cached_graph(repo_id, head_sha, head)

    t2 = time.perf_counter()
    changes = compute_changes(base, head)
    unpack_session: UnpackSession | None = None
    link_outcome: LinkOutcome | None = None
    sources: dict[str, str] | None = None
    if session_payload is not None:
        files = changed_files or []
        known_paths = set(head.mods.keys()) | set(base.mods.keys()) | {
            f["path"] for f in files if isinstance(f.get("path"), str)
        }
        if str(session_payload.get("agent") or "") == AGY_AGENT:
            unpack_session = parse_agy_transcript(session_payload, known_paths=known_paths)
            reconstruct_edit_states(unpack_session, {
                f["path"]: f["base_content"] for f in files
                if isinstance(f.get("path"), str) and isinstance(f.get("base_content"), str)
            })
        else:
            unpack_session = parse_gemini_session(session_payload, known_paths=known_paths)
        link_outcome = link_session_to_changes(unpack_session, changes, base, head, files)
        sources = link_outcome.sources
    build = build_graph_view(changes, base, head, parse_diff_hunks(diff_text), sources=sources)
    try:
        validate_graph_view(build, settings.MAX_GRAPH_NODES, settings.MAX_GRAPH_EDGES)
    except InvalidGraphView as exc:
        raise BuildFailed("invalid_graph_view", str(exc)) from exc
    timings["view_s"] = time.perf_counter() - t2
    return AnalysisBuild(build=build, timings=timings, changes=changes,
                         unpack_session=unpack_session, link_outcome=link_outcome)


def full_graph_for(repo_id: int, mirror: str, sha: str) -> Any:
    """Whole-repo head graph for one commit. Used by the read endpoints when the cache is cold."""
    return build_graph(GitSource(mirror, sha), reach=True)


_pool: ProcessPoolExecutor | None = None


def _executor() -> ProcessPoolExecutor | None:
    global _pool
    if settings.ANALYSIS_PROCESSES <= 0:
        return None
    if _pool is None:
        # spawn, not fork: the worker process has threads and an event loop running.
        _pool = ProcessPoolExecutor(max_workers=settings.ANALYSIS_PROCESSES,
                                    mp_context=multiprocessing.get_context("spawn"))
    return _pool


async def run_analysis(**kwargs: Any) -> AnalysisBuild:
    pool = _executor()
    call = functools.partial(analyze_blocking, **kwargs)
    if pool is None:
        return await asyncio.to_thread(call)
    return await asyncio.get_running_loop().run_in_executor(pool, call)


def shutdown_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None
