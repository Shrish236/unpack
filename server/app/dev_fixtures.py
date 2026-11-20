"""Made-up finished sessions, so every dashboard section and the PR graph have something to draw before real runs.

    python -m server.app.dev_fixtures           add 15 fake sessions spread over the last nine weeks
    python -m server.app.dev_fixtures --clear   remove them again

Every row hangs off one repo, `unpack-dev/fake-sessions`, so nothing here can be mistaken for real data and
`--clear` removes exactly what this made. The rows go through the same tables the pipeline writes, and the
decisions go through the same `attach_nodes_and_outcomes` the pipeline uses, so the dashboards see what real
sessions would give them. The seed is fixed: the same call gives the same sessions.
"""

from __future__ import annotations

import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select

from .db import session_scope
from .models import (
    Analysis, Decision, FunctionReason, Push, Repo, ReviewFinding, Session, SessionSignals,
)
from .pipeline.decision_links import attach_nodes_and_outcomes
from .pipeline.flow import build_flow

OWNER, NAME = "unpack-dev", "fake-sessions"
AREAS = ["payments/client", "payments/ledger", "payments/webhooks", "payments/refunds", "shared/http"]
FUNCS = ["send", "retry", "validate", "build_request", "parse_response", "record", "refund", "sign"]
AGENTS = [("gemini-cli", "gemini-3.5-flash"), ("gemini-cli", "gemini-3.1-pro-preview"), ("antigravity-cli", "gemini-3.5-flash")]
RULE = "Never add a runtime dependency without approval"
# Different wordings of the same correction, so repeated overrides cluster across sessions.
CORRECTIONS = [
    ("dependency", "reject", "Do not add a new runtime dependency for small helpers", "no, don't add tenacity"),
    ("dependency", "reject", "Don't add runtime dependencies for helpers", "please don't pull in a new package"),
    ("test", "requirement", "Every changed function needs a test that reaches it", "add a test for this too"),
    ("retries", "redirect", "Retry with exponential backoff, at most five attempts", "use backoff, not a fixed sleep"),
    ("scope", "redirect", "Keep the change inside the files the ticket names", "only touch the client module"),
]


def _session(i: int, rng: random.Random, now: datetime) -> dict[str, Any]:
    area = AREAS[i % len(AREAS)]
    path = f"{area}/{FUNCS[i % len(FUNCS)]}.py"
    names = rng.sample(FUNCS, rng.randint(2, 4))
    ids = [f"{path}::{n}" for n in names]
    nodes = [{"id": path, "label": path, "kind": "file", "parent": None, "path": path, "layer": "container",
              "imports": [], "imports_total": 0}]
    for k, nid in enumerate(ids):
        nodes.append({
            "id": nid, "label": names[k], "kind": "function", "parent": path, "path": path, "layer": "changed",
            "start_line": 10 + k * 20, "end_line": 24 + k * 20, "signature": f"def {names[k]}(x)", "is_async": False,
            "is_public": True, "bases": [], "imports": [],
            "change": {"kind": rng.choice(["functional", "added", "signature"]), "source": "session"},
            "test": {"label": rng.choice(["direct", "reached", "none"]), "count": 1, "nearest_tested": None},
            "callers_count": 1, "callees_count": 1, "is_test": False, "has_reason": True, "finding_ids": [],
        })
    edges = [{"id": f"{a}>{b}", "source": a, "target": b, "kind": "CALLS", "tier": "EXTRACTED", "via": None}
             for a, b in zip(ids, ids[1:])]
    graph = {"nodes": nodes, "edges": edges, "collapsed": [], "truncated": {"nodes_omitted": 0, "edges_omitted": 0}}
    hunks = [{"id": f"{path}#{k}", "old_start": 10 + k * 20, "old_end": 24 + k * 20, "new_start": 10 + k * 20,
              "new_end": 24 + k * 20, "added": 3, "removed": 1, "owners": [nid], "owner_kind": "function",
              "patch": f"@@ -{10 + k * 20},4 +{10 + k * 20},6 @@ def {names[k]}(x):\n-    return x\n+    value = x + 1\n+    return value"}
             for k, nid in enumerate(ids)]
    hunks.append({"id": f"{path}#imp", "old_start": 1, "old_end": 2, "new_start": 1, "new_end": 3, "added": 1, "removed": 0,
                  "owners": [path], "owner_kind": "module", "patch": "@@ -1,2 +1,3 @@\n+import logging\n import os"})
    order = list(ids)
    flow = build_flow(graph, order)
    rev = list(reversed(ids))
    flow["llm"] = {"mode": "llm", "stages": [{"title": "Fake story", "summary": "Made up for the dev fixtures",
                                              "node_ids": rev, "steps": [{"node": n, "role": "logic", "note": ""} for n in rev]}],
                   "order": rev}
    flow["model"], flow["prompt_version"] = "fake-flow", 1

    day = now - timedelta(days=rng.randint(0, 62))
    timeline = [{"turn": f"T{3 + 3 * k}", "kind": "edit", "ts": day.isoformat(), "label": f"Edited {names[k]}",
                 "nodes": [nid], "reverted": rng.random() < 0.15, "exit_code": None, "finding_id": None}
                for k, nid in enumerate(ids)]
    decisions: list[dict[str, Any]] = []
    for k in range(rng.randint(1, 3)):
        typ, kind, statement, quote = rng.choice(CORRECTIONS)
        decisions.append({"turn": f"T{4 + 3 * k}", "actor": "human", "kind": kind, "type": typ, "proposal": "agent plan",
                          "choice": "human correction", "statement": statement, "quote": quote, "rule_id": "S1" if typ == "dependency" else None,
                          "rule_followed": False if typ == "dependency" else None, "source": "llm"})
    for k in range(rng.randint(1, 3)):
        typ = rng.choice(["architecture", "design", "retries", "test", "scope"])
        decisions.append({"turn": f"T{2 + 3 * k}", "actor": "agent", "kind": "choice", "type": typ, "proposal": "options",
                          "choice": f"agent chose {typ}", "statement": "", "quote": "q", "rule_id": "S1" if k == 0 else None,
                          "rule_followed": rng.random() < 0.8 if k == 0 else None, "source": "llm"})
    findings = [{"kind": "claim_not_backed", "finding": "Claimed a test that does not exist", "functions": ids[:1],
                 "evidence": [{"turn": "T9", "quote": "tests pass"}]}] if rng.random() < 0.3 else []
    attach_nodes_and_outcomes(decisions, [], timeline, findings, nodes)
    flags = [{"flag": f, "path": path, "detail": ""} for f in rng.sample(["new-dependency", "skipped-test", "async-gap"], rng.randint(0, 2))]
    if findings:
        flags.append({"flag": "unsupported", "path": "", "detail": "A claim the session does not back"})
    tested = rng.random() < 0.7
    agent, model = AGENTS[i % len(AGENTS)]
    return {
        "day": day, "path": path, "ids": ids, "graph": graph, "hunks": hunks, "flow": flow, "timeline": timeline,
        "decisions": decisions, "findings": findings, "agent": agent, "model": model, "area": area,
        "signals": {"agent": agent, "attempts": rng.choice([1, 1, 2, 3]), "session_key": f"fake-{i}", "flags": flags, "denied": [],
                    "tool_stats": {"read_file": {"calls": rng.randint(5, 30), "tokens": 9000}, "replace": {"calls": rng.randint(2, 9), "tokens": 14000}}},
        "facts": {"last_test_run": {"turn": "T20", "command": "pytest", "exit_code": 0, "summary": "ok"} if tested else None,
                  "tested_after_final_edit": tested},
        "drivers": [rng.choice(["user_asked", "user_asked", "agent_decided", "not_stated"]) for _ in ids],
    }


async def add_fake_sessions(n: int = 15, seed: int = 7, now: datetime | None = None) -> int:
    rng = random.Random(seed)
    now = now or datetime.now(timezone.utc)
    async with session_scope() as db:
        repo = (await db.execute(select(Repo).where(Repo.owner == OWNER, Repo.name == NAME))).scalar_one_or_none()
        if repo is None:
            repo = Repo(owner=OWNER, name=NAME, remote_url=f"https://github.com/{OWNER}/{NAME}.git", default_branch="main",
                        ingest_token_hash=None, status="active")
            db.add(repo)
            await db.flush()
        first = (await db.execute(select(Push).where(Push.repo_id == repo.id))).scalars().all()
        offset = len(first)
        for i in range(n):
            s = _session(offset + i, rng, now)
            sha = f"{offset + i:040x}"
            push = Push(repo_id=repo.id, branch=f"feature/fake-{offset + i}", base_sha="0" * 40, head_sha=sha, has_session=True,
                        session_agent=s["agent"], received_at=s["day"])
            db.add(push)
            await db.flush()
            a = Analysis(
                push_id=push.id, public_id=f"fake{offset + i:04d}".ljust(12, "0"), status="done",
                summary=f"{len(s['ids'])} functions changed in 1 file; fake data", stats={"functions_changed": len(s["ids"]), "by_source": {"session": len(s["ids"])},
                                                                                 "by_change": {}, "not_reached_by_tests": 0},
                facts=s["facts"], graph_view=s["graph"], reading_order=s["ids"], impact={"summary": {}, "by_node": {}},
                diff_hunks={}, diff_files=[{"path": s["path"], "old_path": None, "status": "M", "is_binary": False, "truncated": False,
                                            "no_patch": False, "added": 4 * len(s["ids"]), "removed": len(s["ids"]), "hunks": s["hunks"]}],
                flow=s["flow"], timeline=s["timeline"], llm_model=s["model"], prompt_version=2,
                created_at=s["day"], finished_at=s["day"],
            )
            db.add(a)
            await db.flush()
            for nid, driver in zip(s["ids"], s["drivers"]):
                db.add(FunctionReason(analysis_id=a.id, node_id=nid, reason=f"Fake reason for {nid.split('::')[1]}", driver=driver,
                                      history=[], confidence="high", evidence=[], source="session"))
            for f in s["findings"]:
                db.add(ReviewFinding(analysis_id=a.id, kind=f["kind"], finding=f["finding"], functions=f["functions"], evidence=f["evidence"]))
            for d in s["decisions"]:
                db.add(Decision(analysis_id=a.id, turn=int(d["turn"][1:]), actor=d["actor"], kind=d["kind"], type=d["type"],
                                proposal=d["proposal"], choice=d["choice"], statement=d["statement"], quote=d["quote"],
                                rule_id=d["rule_id"], rule_followed=d["rule_followed"], source=d["source"],
                                node_ids=d["nodes"], outcome=d["outcome"]))
            db.add(SessionSignals(analysis_id=a.id, signals=s["signals"], highlights=[],
                                  steering={"files": {"GEMINI.md": 1}, "rules": [{"id": "S1", "text": RULE, "source": "GEMINI.md", "section": "Deps"}]}))
            db.add(Session(push_id=push.id, agent=s["agent"], file_name="fake.jsonl", turns=[]))
    return n


async def clear_fake_sessions() -> int:
    async with session_scope() as db:
        repo = (await db.execute(select(Repo).where(Repo.owner == OWNER, Repo.name == NAME))).scalar_one_or_none()
        if repo is None:
            return 0
        pushes = list((await db.execute(select(Push.id).where(Push.repo_id == repo.id))).scalars())
        analyses = list((await db.execute(select(Analysis.id).where(Analysis.push_id.in_(pushes)))).scalars()) if pushes else []
        if analyses:
            for model in (FunctionReason, ReviewFinding, Decision, SessionSignals):
                await db.execute(delete(model).where(model.analysis_id.in_(analyses)))
            await db.execute(delete(Analysis).where(Analysis.id.in_(analyses)))
        if pushes:
            await db.execute(delete(Session).where(Session.push_id.in_(pushes)))
            await db.execute(delete(Push).where(Push.id.in_(pushes)))
        await db.execute(delete(Repo).where(Repo.id == repo.id))
        return len(analyses)


async def _main(argv: list[str]) -> None:
    from .pipeline.rollup import rollup_measured
    if "--clear" in argv:
        print(f"removed {await clear_fake_sessions()} fake sessions")
    else:
        print(f"added {await add_fake_sessions()} fake sessions")
    print(await rollup_measured())


if __name__ == "__main__":
    asyncio.run(_main(sys.argv[1:]))
