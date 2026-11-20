"""Analysis of one push: code graph facts, session parsing, edit linking, LLM reasoning & verification (§4, §6)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..config import settings
from ..llm.client import LLMCallRecord, run_reasoning_llm
from ..llm.prompt_builder import build_reasoning_prompt
from .build import BuildFailed, run_analysis
from .edit_linker import LinkOutcome
from .graph_view import GraphBuild
from .payload import build_overlay, changed_python_files, needs_head_fetch
from .repos import CommitUnavailable, ensure_commit, ensure_mirror
from .verify import TEXT_ONLY_REASON, verify_reasoning_output

log = logging.getLogger("unpack.analysis")


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
    session_turns: list[dict[str, Any]] = field(default_factory=list)
    llm_calls: list[LLMCallRecord] = field(default_factory=list)
    claim_turns: list[tuple[str, str, int]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


def _summary(build: GraphBuild, file_count: int) -> str:
    n = build.stats["functions_changed"]
    if n == 0:
        return "No Python functions changed."
    untested = build.stats["not_reached_by_tests"]
    files = f"{file_count} file" + ("" if file_count == 1 else "s")
    tail = f"; {untested} not reached by any test" if untested else "; all reached by a test"
    return f"{n} function{'s' if n != 1 else ''} changed in {files}{tail}."


def _text_only_reasons(
    text_only_ids: list[str], link_outcome: LinkOutcome
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for nid in text_only_ids:
        link = link_outcome.links.get(nid)
        source = link.source if link else "outside_session"
        driver = "agent_decided" if source in ("session", "session_then_formatted") else "not_stated"
        out[nid] = {
            "reason": TEXT_ONLY_REASON,
            "driver": driver,
            "history": [],
            "confidence": "high",
            "source": source,
            "evidence": [],
            "rejected": None,
        }
    return out


async def analyze_push(
    *,
    repo_id: int,
    owner: str,
    name: str,
    remote_url: str,
    token: str | None,
    payload: dict[str, Any],
    daily_tokens_used: int = 0,
) -> AnalysisOutcome:
    base_sha = payload["base_sha"]
    head_sha = payload["head_sha"]
    changed_files = payload.get("changed_files", [])
    session_payload = payload.get("session")

    try:
        mirror = await ensure_mirror(owner, name, remote_url, token)
    except Exception as exc:  # git clone failed
        raise AnalysisFailed("graph_unavailable", f"could not clone the repository: {exc}") from exc
    try:
        await ensure_commit(mirror, base_sha, token)
    except CommitUnavailable as exc:
        raise AnalysisFailed("graph_unavailable", f"base commit unavailable: {exc}") from exc

    overlay, removed = build_overlay(changed_files)
    full_head = needs_head_fetch(changed_files)
    if full_head:
        try:
            await ensure_commit(mirror, head_sha, token)
        except CommitUnavailable as exc:
            raise AnalysisFailed(
                "graph_unavailable",
                "a changed file was too large to send and the head commit is not on GitHub yet",
            ) from exc

    try:
        analysis_build = await run_analysis(
            repo_id=repo_id, mirror=str(mirror), base_sha=base_sha, head_sha=head_sha,
            overlay=overlay, removed=sorted(removed), diff_text=payload.get("diff", ""),
            full_head=full_head, changed_files=changed_files, session_payload=session_payload,
        )
    except BuildFailed as exc:
        raise AnalysisFailed(exc.code, exc.message) from exc
    except AnalysisFailed:
        raise
    except Exception as exc:
        raise AnalysisFailed("graph_failed", f"code graph build failed: {type(exc).__name__}") from exc
    build = analysis_build.build
    unpack_session = analysis_build.unpack_session
    link_outcome = analysis_build.link_outcome

    changed_count = build.stats["functions_changed"]
    file_count = len({n["path"] for n in build.graph["nodes"] if n["layer"] in ("changed", "ghost")})
    session_turns = unpack_session.to_turn_details() if unpack_session else []
    facts = (
        link_outcome.facts_dict()
        if link_outcome is not None
        else {"last_test_run": None, "tested_after_final_edit": False}
    )
    timeline = list(link_outcome.timeline) if link_outcome is not None else []

    reasons: dict[str, dict[str, Any]] = {}
    findings: list[dict[str, Any]] = []
    claim_turns: list[tuple[str, str, int]] = []
    llm_calls: list[LLMCallRecord] = []
    llm_model: str | None = None
    rejected_count = 0
    summary = _summary(build, file_count)
    banner: dict[str, str] | None = None

    if changed_count == 0:
        banner = None
    elif unpack_session is None or link_outcome is None:
        banner = {
            "kind": "no_session",
            "message": "No agent session was sent for this push. Every change is listed as outside the session.",
        }
    elif not settings.REASONING_ENABLED:
        banner = {
            "kind": "reasons_unavailable",
            "message": "Reasons are not generated in this build yet.",
        }
    else:
        built = build_reasoning_prompt(
            unpack_session,
            link_outcome,
            build.graph["nodes"],
            build.reading_order,
            prompt_version=settings.PROMPT_VERSION,
        )
        if not built.target_node_ids:
            # Only text_only functions changed -> auto-label locally without calling Gemini
            reasons = _text_only_reasons(built.text_only_node_ids, link_outcome)
            banner = None
        else:
            llm_res = await run_reasoning_llm(
                system_prompt=built.system_prompt,
                user_prompt=built.user_prompt,
                prompt_version=settings.PROMPT_VERSION,
                daily_tokens_used=daily_tokens_used,
            )
            llm_calls = llm_res.calls
            if llm_res.output is None:
                # Degrade gracefully: keep graph, parsed turns, provenance, facts, timeline
                log.warning("reasoning degraded for %s/%s@%s: %s", owner, name, head_sha[:7], llm_res.error)
                reasons = _text_only_reasons(built.text_only_node_ids, link_outcome)
                banner = {
                    "kind": "reasons_unavailable",
                    "message": "AI reasoning was unavailable for this push; code graph and session facts are shown.",
                }
            else:
                verified = verify_reasoning_output(
                    llm_res.output,
                    session=unpack_session,
                    link_outcome=link_outcome,
                    alias_to_node=built.alias_to_node,
                    target_node_ids=built.target_node_ids,
                    text_only_node_ids=built.text_only_node_ids,
                    graph_nodes=build.graph["nodes"],
                )
                reasons = verified.reasons
                findings = verified.findings
                claim_turns = verified.claim_turns
                rejected_count = verified.rejected_count
                llm_model = llm_res.model
                if verified.summary:
                    summary = verified.summary
                banner = None

    # Mark has_reason on changed graph nodes
    for node in build.graph["nodes"]:
        if node["id"] in reasons:
            node["has_reason"] = True

    return AnalysisOutcome(
        summary=summary,
        banner=banner,
        stats=build.stats,
        facts=facts,
        graph_view=build.graph,
        reading_order=build.reading_order,
        impact=build.impact,
        diff_hunks=build.diff_hunks,
        timeline=timeline,
        reasons=reasons,
        findings=findings,
        not_reached=build.not_reached,
        changed_count=changed_count,
        has_python_changes=bool(changed_python_files(changed_files)),
        llm_model=llm_model,
        rejected_count=rejected_count,
        file_count=file_count,
        head_graph_cached=True,
        session_turns=session_turns,
        llm_calls=llm_calls,
        claim_turns=claim_turns,
    )
