"""Analysis of one push: code graph facts, session parsing, edit linking, LLM reasoning & verification (§4, §6)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from ..config import settings
from ..llm.client import LLMCallRecord, run_reasoning_llm
from ..llm.prompt_builder import build_reasoning_prompt
from .decisions import extract_decisions
from .signals import compute_signals
from .steering import SteeringSnapshot, read_steering
from .build import BuildFailed, run_analysis
from .agy_session import AGY_AGENT, parse_agy_transcript
from .session import UnpackSession, parse_gemini_session
from .edit_linker import LinkOutcome
from .graph_view import GraphBuild
from .payload import build_overlay, changed_python_files, needs_head_fetch
from ..llm.graph_context import GraphTools, build_code_context
from ..llm.graph_notes import graph_notes
from .repos import CommitUnavailable, ensure_commit, ensure_mirror, has_commit, load_cached_graph, read_file_at
from .verify import TEXT_ONLY_REASON, verify_reasoning_output

log = logging.getLogger("unpack.analysis")


class AnalysisFailed(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.governance: Any = None  # a GovernanceOutcome, set when the session was still analysed
        self.session_turns: list[dict[str, Any]] = []


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
    signals: dict[str, Any] = field(default_factory=dict)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    highlights: list[dict[str, Any]] = field(default_factory=list)
    steering: dict[str, Any] = field(default_factory=dict)


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


@dataclass
class GovernanceOutcome:
    signals: dict[str, Any] = field(default_factory=dict)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    highlights: list[dict[str, Any]] = field(default_factory=list)
    steering: dict[str, Any] = field(default_factory=dict)
    llm_calls: list[LLMCallRecord] = field(default_factory=list)


async def governance_pass(
    session: UnpackSession, *, diff_text: str, mirror: Any | None, base_sha: str, head_sha: str,
    findings: list[dict[str, Any]], daily_tokens_used: int = 0, code_context: str | None = None,
) -> GovernanceOutcome:
    """Signals, steering and decisions for one session. Never raises: a failure is recorded in the signals."""
    out = GovernanceOutcome()
    try:
        out.signals = compute_signals(session, diff_text)
        if any(f.get("kind") == "claim_not_backed" for f in findings):
            out.signals["flags"].append({"flag": "unsupported", "path": "", "detail": "A claim the session does not back"})
        steering = SteeringSnapshot(files={}, rules=[])
        if mirror is not None:
            try:
                steer_sha = head_sha if await has_commit(mirror, head_sha) else base_sha
                steering = await asyncio.to_thread(read_steering, mirror, steer_sha)
            except Exception as exc:  # no steering is fine
                log.warning("steering unavailable: %s", exc)
        out.steering = steering.as_json()
        dec = await extract_decisions(session, steering, out.signals, daily_tokens_used=daily_tokens_used, code_context=code_context)
        out.decisions, out.highlights, out.llm_calls = dec.decisions, dec.highlights, dec.llm_calls
        out.signals["decision_error"] = dec.error
        out.signals["decisions_rejected"] = dec.rejected_count
    except Exception as exc:
        log.exception("governance pass failed: %s", exc)
        out.signals = out.signals or {}
        out.signals["decision_error"] = f"{type(exc).__name__}: {exc}"
    return out


async def analyze_push(**kwargs: Any) -> AnalysisOutcome:
    """Graph analysis plus the governance pass. When the graph cannot be built, the session's metrics are kept anyway."""
    try:
        return await _analyze_push(**kwargs)
    except AnalysisFailed as exc:
        payload = kwargs["payload"]
        raw = payload.get("session")
        if raw is not None:
            try:
                paths = {f["path"] for f in payload.get("changed_files", []) if isinstance(f.get("path"), str)}
                if str(raw.get("agent") or "") == AGY_AGENT:
                    session = parse_agy_transcript(raw, known_paths=paths)
                else:
                    session = parse_gemini_session(raw, known_paths=paths)
                exc.governance = await governance_pass(
                    session, diff_text=payload.get("diff", ""), mirror=None, base_sha=payload["base_sha"],
                    head_sha=payload["head_sha"], findings=[], daily_tokens_used=kwargs.get("daily_tokens_used", 0),
                )
                exc.session_turns = session.to_turn_details()
            except Exception:
                log.exception("governance after a failed analysis also failed")
        raise


async def _analyze_push(
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

    head_graph = load_cached_graph(repo_id, head_sha) if settings.GRAPH_CONTEXT_ENABLED else None
    head_contents = {f["path"]: f.get("head_content") for f in changed_files if isinstance(f.get("path"), str)}

    def read_source(path: str) -> str | None:
        if isinstance(head_contents.get(path), str):
            return head_contents[path]
        try:
            return read_file_at(mirror, base_sha, path).decode("utf-8", "replace")
        except Exception:
            return None

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
            graph=head_graph,
        )
        if not built.target_node_ids:
            # Only text_only functions changed -> auto-label locally without calling Gemini
            reasons = _text_only_reasons(built.text_only_node_ids, link_outcome)
            banner = None
        else:
            user_prompt = built.user_prompt
            if head_graph is not None:
                tools = GraphTools(head_graph, read_source)
                first_task = next((t.text for t in unpack_session.turns if t.kind == "user"), "")
                notes, note_calls = await graph_notes(tools, changed=built.target_node_ids, task=first_task)
                llm_calls = llm_calls + note_calls
                if notes:
                    user_prompt += "\n\n## CODE NOTES (from graph lookups. Context only, never evidence)\n" + notes
            llm_res = await run_reasoning_llm(
                system_prompt=built.system_prompt,
                user_prompt=user_prompt,
                prompt_version=settings.PROMPT_VERSION,
                daily_tokens_used=daily_tokens_used,
            )
            llm_calls = llm_calls + llm_res.calls
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

    # Governance pass: signals (no LLM), steering rules, and decisions. It must never fail the analysis.
    gov = GovernanceOutcome()
    if unpack_session is not None:
        changed_ids = list(link_outcome.links)[: settings.MAX_LLM_FUNCTIONS] if link_outcome is not None else []
        code_context = build_code_context(head_graph, changed_ids) if head_graph is not None and changed_ids else None
        gov = await governance_pass(
            unpack_session, diff_text=payload.get("diff", ""), mirror=mirror, base_sha=base_sha, head_sha=head_sha,
            findings=findings, daily_tokens_used=daily_tokens_used, code_context=code_context,
        )
        # A tool call the human refused is a point on the timeline, on the human side.
        for d in gov.signals.get("denied", []):
            t = unpack_session.turns_by_id[d["turn"]]
            timeline.append({
                "turn": d["turn"], "kind": "denied", "ts": t.ts, "label": f"Denied: {d['target']}"[:120],
                "nodes": [], "reverted": False, "exit_code": None, "finding_id": None,
            })
        timeline.sort(key=lambda e: int(str(e["turn"]).lstrip("T") or 0))
        llm_calls = llm_calls + gov.llm_calls
    signals, decisions, highlights, steering_json = gov.signals, gov.decisions, gov.highlights, gov.steering

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
        signals=signals,
        decisions=decisions,
        highlights=highlights,
        steering=steering_json,
    )
