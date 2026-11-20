"""Live graph API: analyses, turns, node details, commit picker, codebase map (server design §5.5, §5.6)."""

from __future__ import annotations

import gzip
import re
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import require_repo_access, viewer
from ..errors import ApiError
from ..jobs.handlers import ensure_head_graph, read_payload
from ..models import Analysis, FunctionReason, PRAnalysis, PullRequest, Push, Repo, ReviewFinding, Session, User
from ..pipeline.analysis import AnalysisFailed
from ..pipeline.graph_view import _callees, _callers, _nearest_tested
from ..pipeline.repos import data_dir, repo_dir, read_file_at
from ..schemas.api import (
    AnalysisFacts,
    AnalysisMetadata,
    AnalysisResponse,
    AnalysisStats,
    Banner,
    DiffHunk,
    GraphPayload,
    ImpactData,
    PullRequestInfo,
    RepoRef,
    ReviewFinding as ReviewFindingModel,
    FunctionReason as FunctionReasonModel,
    TimelineTurn,
)
from ..services import get_github

router = APIRouter()
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_SOURCE_LINES = 400


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def _analysis_by_public_id(db: AsyncSession, public_id: str) -> tuple[Analysis, Push, Repo]:
    analysis = (await db.execute(select(Analysis).where(Analysis.public_id == public_id))).scalar_one_or_none()
    if analysis is None:
        raise ApiError(404, "not_found", "no such analysis")
    push = await db.get(Push, analysis.push_id)
    repo = await db.get(Repo, push.repo_id)
    return analysis, push, repo


async def _repo_by_name(db: AsyncSession, owner: str, name: str) -> Repo:
    repo = (await db.execute(select(Repo).where(
        Repo.owner.ilike(owner), Repo.name.ilike(name)))).scalar_one_or_none()
    if repo is None:
        raise ApiError(404, "not_found", "no such repository")
    return repo


async def _graph_or_404(*args: Any) -> Any:
    """The whole-repo graph for a commit. A commit the server cannot reach is a 404, not a server error."""
    try:
        return await ensure_head_graph(*args)
    except AnalysisFailed as exc:
        raise ApiError(404, "not_found", f"the code graph for this commit is not available ({exc.code})") from exc


async def _repo_token(repo: Repo) -> str | None:
    if repo.installation_id is None:
        return None
    return await get_github().installation_token(repo.installation_id)


async def _pr_for_analysis(db: AsyncSession, analysis: Analysis, push: Push) -> PullRequestInfo | None:
    pr = (await db.execute(
        select(PullRequest)
        .join(PRAnalysis, PRAnalysis.pr_id == PullRequest.id)
        .where(PRAnalysis.analysis_id == analysis.id, PullRequest.repo_id == push.repo_id)
        .limit(1)
    )).scalar_one_or_none()
    if pr is None:
        return None
    return PullRequestInfo(number=pr.number, title=pr.title or "", url=pr.html_url or "",
                           state="merged" if pr.state == "merged" else ("closed" if pr.state == "closed" else "open"))


async def _build_analysis(db: AsyncSession, analysis: Analysis, push: Push, repo: Repo) -> AnalysisResponse:
    reasons_rows = (await db.execute(select(FunctionReason).where(FunctionReason.analysis_id == analysis.id))).scalars().all()
    findings_rows = (await db.execute(select(ReviewFinding).where(ReviewFinding.analysis_id == analysis.id))).scalars().all()
    reasons = {
        r.node_id: FunctionReasonModel(reason=r.reason, driver=r.driver, history=r.history,
                                       confidence=r.confidence, source=r.source, evidence=r.evidence or [])
        for r in reasons_rows
    }
    findings = [ReviewFindingModel(id=f.id, kind=f.kind, finding=f.finding, functions=f.functions or [],
                                   evidence=f.evidence or []) for f in findings_rows]
    timeline = [TimelineTurn(**t) for t in (analysis.timeline or [])]
    metadata = AnalysisMetadata(
        public_id=analysis.public_id,
        status=analysis.status,
        repo=RepoRef(owner=repo.owner, name=repo.name, default_branch=repo.default_branch),
        branch=push.branch,
        base_sha=push.base_sha,
        head_sha=push.head_sha,
        short_sha=push.head_sha[:7],
        created_at=_iso(analysis.created_at) or "",
        finished_at=_iso(analysis.finished_at),
        agent=push.session_agent,
        llm_model=analysis.llm_model,
        prompt_version=analysis.prompt_version,
        has_session=push.has_session,
        error_code=analysis.error_code,
        error_message=analysis.error_message,
    )
    return AnalysisResponse(
        analysis=metadata,
        pull_request=await _pr_for_analysis(db, analysis, push),
        banner=Banner(**analysis.banner) if analysis.banner else None,
        summary=analysis.summary or "",
        stats=AnalysisStats(**analysis.stats) if analysis.stats else AnalysisStats(functions_changed=0),
        facts=AnalysisFacts(**analysis.facts) if analysis.facts else AnalysisFacts(),
        graph=GraphPayload(**analysis.graph_view) if analysis.graph_view else GraphPayload(),
        reading_order=analysis.reading_order or [],
        impact=ImpactData(**analysis.impact) if analysis.impact else ImpactData(),
        timeline=timeline,
        reasons=reasons,
        findings=findings,
        diff_hunks={k: [DiffHunk(**h) for h in v] for k, v in (analysis.diff_hunks or {}).items()},
    )


@router.get("/api/analyses/{public_id}")
async def get_analysis(public_id: str, request: Request, auth: tuple[User, str] = Depends(viewer), db: AsyncSession = Depends(get_db)) -> Response:
    analysis, push, repo = await _analysis_by_public_id(db, public_id)
    await require_repo_access(db, auth[0], auth[1], repo)
    if analysis.status in ("queued", "running"):
        body = {"analysis": {"public_id": public_id, "status": analysis.status}}
        return JSONResponse(body, status_code=200, headers={"Retry-After": "3"})
    if analysis.status == "failed":
        body = {"analysis": {"public_id": public_id, "status": "failed",
                             "error_code": analysis.error_code, "error_message": analysis.error_message},
                "repo": {"owner": repo.owner, "name": repo.name}, "branch": push.branch,
                "head_sha": push.head_sha, "short_sha": push.head_sha[:7]}
        return JSONResponse(body, status_code=200)
    model = await _build_analysis(db, analysis, push, repo)
    return JSONResponse(model.model_dump(mode="json", by_alias=True))


@router.get("/api/analyses/{public_id}/turns")
async def get_turns(public_id: str, request: Request, ids: str = "", auth: tuple[User, str] = Depends(viewer), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    analysis, push, repo = await _analysis_by_public_id(db, public_id)
    await require_repo_access(db, auth[0], auth[1], repo)
    wanted = [i.strip() for i in ids.split(",") if i.strip()]
    if not wanted or len(wanted) > 50:
        raise ApiError(400, "invalid_ids", "ids must contain 1 to 50 turn IDs")
    session_row = (await db.execute(select(Session).where(Session.push_id == push.id))).scalar_one_or_none()
    turns = (session_row.turns if session_row else []) or []
    found = [t for t in turns if t.get("turn_id") in wanted]
    return {"turns": found}


def _source_text(push: Push, repo: Repo, path: str, start: int, end: int, head_sha: str) -> str:
    """Source of one function at head: one blob from the mirror, else the payload's copy of the file."""
    lines: list[str] = []
    mirror = repo_dir(repo.owner, repo.name)
    if mirror.exists():
        try:
            lines = read_file_at(mirror, head_sha, path).decode("utf-8", errors="replace").splitlines()
        except Exception:  # commit or path not in the mirror (yet)
            lines = []
    if not lines:
        data = read_payload(push.payload_path)
        for f in data.get("changed_files", []):
            if f["path"] == path and f.get("head_content") is not None:
                lines = f["head_content"].splitlines()
                break
    if not lines:
        return ""
    return "\n".join(lines[start - 1 : min(end, start - 1 + MAX_SOURCE_LINES)])


@router.get("/api/analyses/{public_id}/nodes/{node_id:path}")
async def get_node(public_id: str, node_id: str, request: Request, auth: tuple[User, str] = Depends(viewer), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    analysis, push, repo = await _analysis_by_public_id(db, public_id)
    await require_repo_access(db, auth[0], auth[1], repo)
    if analysis.status != "done":
        raise ApiError(404, "not_found", "analysis is not finished")
    token = await _repo_token(repo)
    remote = f"https://github.com/{repo.owner}/{repo.name}.git"
    head = await _graph_or_404(repo.id, repo.owner, repo.name, repo.remote_url or remote, token, push.head_sha)
    graph_nodes = {n["id"]: n for n in (analysis.graph_view or {}).get("nodes", [])}
    in_graph = set(graph_nodes)

    func = head.funcs.get(node_id)
    module_path = node_id if node_id in head.mods else None
    cls = next((c for c in head.classes.values() if c.id == node_id), None)
    if func is None and module_path is None and cls is None:
        raise ApiError(404, "not_found", "no such node")

    if func is not None:
        path, start, end = func.path, func.start, func.end
        node = {
            "id": func.id, "kind": "method" if func.is_method else "function", "path": func.path,
            "start_line": func.start, "end_line": func.end, "signature": func.signature,
            "decorators": list(func.decorators), "is_async": func.is_async,
            "is_public": not func.name.startswith("_"),
            "doc": (func.doc or "").strip().splitlines()[0] if func.doc else None,
        }
        class_id = None
        if func.is_method and "." in func.qualname:
            class_id = f"{func.path}::{func.qualname.rsplit('.', 1)[0]}"
            cinfo = next((c for c in head.classes.values() if c.id == class_id), None)
            node["class"] = {"id": class_id, "bases": list(cinfo.bases_raw) if cinfo else []}
        reach = head.reach.get(node_id)
        if reach and reach.label in ("direct", "reached", "reached_uncertain"):
            tests = {"label": reach.label, "count": reach.count,
                     "paths": [list(reach.path)] if reach.path else [], "nearest_tested": None}
        else:
            nearest = _nearest_tested(head, node_id)
            near = None
            if nearest:
                nr = head.reach.get(nearest)
                near = {"id": nearest, "count": nr.count if nr else 0, "path": list(nr.path) if nr else []}
            tests = {"label": "none", "count": 0, "paths": [], "nearest_tested": near}
        all_callers = _callers(head, node_id)
        all_callees = _callees(head, node_id)
        callers = [
            {"id": e.src, "tier": e.tier, "via": e.via,
             "line": e.lines[0] if e.lines else None, "in_graph": e.src in in_graph}
            for e in all_callers[:100]
        ]
        callees = [
            {"id": e.dst, "tier": e.tier, "via": e.via,
             "line": e.lines[0] if e.lines else None, "in_graph": e.dst in in_graph}
            for e in all_callees[:100]
        ]
        unresolved = [{"line": line, "raw": raw, "reason": reason}
                      for line, raw, reason in head.unresolved.get(node_id, [])[:100]]
    elif cls is not None:
        path, start, end = cls.path, cls.start, cls.end
        node = {"id": cls.id, "kind": "class", "path": cls.path, "start_line": cls.start,
                "end_line": cls.end, "signature": f"class {cls.name}", "decorators": list(cls.decorators),
                "is_async": False, "is_public": not cls.name.startswith("_"),
                "doc": None, "class": None}
        tests = {"label": "none", "count": 0, "paths": [], "nearest_tested": None}
        callers, callees, unresolved, all_callers, all_callees = [], [], [], [], []
    else:
        mod = head.mods[module_path]
        path, start, end = module_path, 1, max(mod.nlines, 1)
        node = {"id": module_path, "kind": "file", "path": module_path, "start_line": 1,
                "end_line": end, "signature": "", "decorators": [], "is_async": False,
                "is_public": True, "doc": None, "class": None}
        tests = {"label": "none", "count": 0, "paths": [], "nearest_tested": None}
        callers, callees, unresolved, all_callers, all_callees = [], [], [], [], []

    module_name = path[:-3].replace("/", ".") if path.endswith(".py") else path
    file_imports = []
    mod = head.mods.get(path)
    if mod is not None:
        for imp in mod.imports:
            names = [n for n, _ in imp.names] if imp.names else []
            file_imports.append({"module": imp.module, "names": names, "context": imp.context})
    file_imported_by = sorted({
        p for p, m in head.mods.items()
        if p != path and any(i.module == module_name or i.module.startswith(module_name + ".") for i in m.imports)
    })

    change = graph_nodes.get(node_id, {}).get("change")
    diff = (analysis.diff_hunks or {}).get(node_id, [])
    impact = (analysis.impact or {}).get("by_node", {}).get(node_id, [])
    source_head = _source_text(push, repo, path, start, end, push.head_sha) if path else ""
    return {
        "node": node,
        "change": change,
        "source_head": source_head,
        "diff": diff,
        "callers": callers,
        "callees": callees,
        "callers_total": len(all_callers),
        "callees_total": len(all_callees),
        "unresolved_calls": unresolved,
        "file_imports": file_imports,
        "file_imported_by": file_imported_by,
        "tests": tests,
        "impact": impact,
    }


@router.get("/api/prs/{owner}/{repo}/{number}/analyses")
async def pr_analyses(owner: str, repo: str, number: int, request: Request, auth: tuple[User, str] = Depends(viewer), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    repo_row = await _repo_by_name(db, owner, repo)
    await require_repo_access(db, auth[0], auth[1], repo_row)
    pr = (await db.execute(select(PullRequest).where(
        PullRequest.repo_id == repo_row.id, PullRequest.number == number))).scalar_one_or_none()
    if pr is None:
        raise ApiError(404, "not_found", "no such pull request")
    rows = (await db.execute(
        select(Analysis, Push)
        .join(PRAnalysis, PRAnalysis.analysis_id == Analysis.id)
        .join(Push, Push.id == Analysis.push_id)
        .where(PRAnalysis.pr_id == pr.id)
        .order_by(Analysis.id.desc())
        .limit(50)
    )).all()
    analyses = []
    for analysis, push in rows:
        message = next((c.get("message", "") for c in (push.commits or []) if c.get("sha") == push.head_sha), "")
        analyses.append({
            "public_id": analysis.public_id,
            "head_sha": push.head_sha,
            "short_sha": push.head_sha[:7],
            "commit_message": message.splitlines()[0] if message else "",
            "created_at": _iso(analysis.created_at),
            "status": analysis.status,
            "is_published": pr.last_published_analysis_id == analysis.id,
        })
    return {
        "pull_request": {"number": pr.number, "title": pr.title or "", "url": pr.html_url or "", "state": pr.state},
        "analyses": analyses,
    }


def _map_rows(head: Any) -> tuple[list[list[Any]], dict[str, int]]:
    rows: list[list[Any]] = []
    folders: set[str] = set()
    counts = {"folders": 0, "files": 0, "classes": 0, "functions": 0, "tests": 0}
    folder_loc: dict[str, int] = {}
    for path, mod in sorted(head.mods.items()):
        parts = path.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            folder = "/".join(parts[:i])
            folders.add(folder)
            folder_loc[folder] = folder_loc.get(folder, 0) + mod.nlines  # lines under the folder
    for folder in sorted(folders):
        parent = folder.rsplit("/", 1)[0] if "/" in folder else None
        rows.append([folder, "folder", parent, folder_loc.get(folder, 0), 0, False])
        counts["folders"] += 1
    for path, mod in sorted(head.mods.items()):
        parent = path.rsplit("/", 1)[0] if "/" in path else None
        rows.append([path, "file", parent, mod.nlines, 0, mod.is_test])
        counts["files"] += 1
    for cls in sorted(head.classes.values(), key=lambda c: c.id):
        rows.append([cls.id, "class", cls.path, max(cls.end - cls.start + 1, 0), 0, False])
        counts["classes"] += 1
    for fid, func in sorted(head.funcs.items()):
        parent = f"{func.path}::{func.qualname.rsplit('.', 1)[0]}" if func.is_method and "." in func.qualname else func.path
        kind = "test" if func.is_test else ("method" if func.is_method else "function")
        rows.append([fid, kind, parent, max(func.end - func.start + 1, 0),
                     len(_callers(head, fid)), func.is_test])
        if func.is_test:
            counts["tests"] += 1
        else:
            counts["functions"] += 1
    return rows, counts


@router.get("/api/repos/{owner}/{repo}/map")
async def codebase_map(owner: str, repo: str, sha: str, request: Request, auth: tuple[User, str] = Depends(viewer), db: AsyncSession = Depends(get_db)) -> Response:
    if not SHA_RE.match(sha):
        raise ApiError(400, "invalid_payload", "sha must be 40 lowercase hex characters")
    repo_row = await _repo_by_name(db, owner, repo)
    await require_repo_access(db, auth[0], auth[1], repo_row)
    etag = f'"{sha}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "private, max-age=86400"})
    cache = data_dir() / "maps" / str(repo_row.id) / f"{sha}.json.gz"
    if cache.exists():
        body = gzip.decompress(cache.read_bytes())
    else:
        token = await _repo_token(repo_row)
        remote = repo_row.remote_url or f"https://github.com/{repo_row.owner}/{repo_row.name}.git"
        head = await _graph_or_404(repo_row.id, repo_row.owner, repo_row.name, remote, token, sha)
        rows, counts = _map_rows(head)
        body = json.dumps({
            "repo": {"owner": repo_row.owner, "name": repo_row.name, "default_branch": repo_row.default_branch},
            "map_sha": sha,
            "columns": ["id", "kind", "parent", "loc", "fan_in", "is_test"],
            "nodes": rows,
            "counts": counts,
        }).encode("utf-8")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(gzip.compress(body))
    return Response(content=body, media_type="application/json",
                    headers={"ETag": etag, "Cache-Control": "private, max-age=86400"})


@router.get("/api/repos/{owner}/{repo}/nodes/{node_id:path}/edges")
async def node_edges(owner: str, repo: str, node_id: str, sha: str, request: Request,
                     auth: tuple[User, str] = Depends(viewer), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    if not SHA_RE.match(sha):
        raise ApiError(400, "invalid_payload", "sha must be 40 lowercase hex characters")
    repo_row = await _repo_by_name(db, owner, repo)
    await require_repo_access(db, auth[0], auth[1], repo_row)
    token = await _repo_token(repo_row)
    remote = repo_row.remote_url or f"https://github.com/{repo_row.owner}/{repo_row.name}.git"
    head = await _graph_or_404(repo_row.id, repo_row.owner, repo_row.name, remote, token, sha)
    if node_id not in head.funcs:
        raise ApiError(404, "not_found", "no such node")
    callers = _callers(head, node_id)
    callees = _callees(head, node_id)
    return {
        "id": node_id,
        "callers": [{"id": e.src, "tier": e.tier} for e in callers[:200]],
        "callees": [{"id": e.dst, "tier": e.tier} for e in callees[:200]],
        "callers_total": len(callers),
        "callees_total": len(callees),
    }
