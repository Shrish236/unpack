// A synthetic large commit for the lab: about 35 changed files in 5 folders, about 100 changed functions, plus a few
// unchanged neighbours. It reuses the rich fixture's header (repo, PR, facts) and replaces the graph, so the page
// can be tried on a size the real fixture does not reach. Deterministic, so screenshots and reviews are repeatable.
import type { AnalysisResponse, GEdge, GNode } from "../api";

const FILES: Record<string, string[]> = {
  "httpx/_transports": ["default", "asgi", "wsgi", "mock", "base", "h2", "h11", "http_proxy", "socks"],
  httpx: ["_client", "_api", "_config", "_models", "_auth", "_utils", "_urls", "_urlparse", "_decoders", "_content", "_multipart", "_exceptions"],
  tests: ["test_client", "test_config", "test_api", "test_models", "test_auth", "test_urls"],
  "tests/client": ["test_async_client", "test_headers", "test_redirects", "test_proxies", "test_cookies"],
  scripts: ["check", "build", "publish"],
};
const NEIGHBOUR_FILES = ["httpx/_internal/pool.py", "httpx/_internal/limits.py", "httpx/_internal/tls.py", "httpx/_internal/events.py"];
const VERBS = ["parse", "build", "send", "read", "write", "merge", "encode", "decode", "resolve", "validate", "close", "open", "get", "set", "handle", "prepare", "wrap", "apply", "iter", "check"];
const NOUNS = ["request", "response", "headers", "url", "body", "stream", "cookie", "auth", "proxy", "timeout", "limits", "config", "event", "chunk", "pool", "socket", "query", "scheme"];
const REASONS = [
  "Moves the transport call behind the new base class so every transport shares one retry path.",
  "Renames the helper to match the new transport interface; callers are updated in the same commit.",
  "Adds the new argument the transport migration needs and keeps the old default for callers.",
  "Replaces the hand-rolled loop with the shared helper, which also handles redirects.",
  "Updates the test to the new transport fixtures.",
];

function rng(seed: number) {
  let s = seed;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function makeLarge(base: AnalysisResponse): AnalysisResponse {
  const rand = rng(11);
  const pick = <T,>(xs: T[]) => xs[Math.floor(rand() * xs.length)];
  const nodes: GNode[] = [];
  const mk = (path: string, name: string, line: number, layer: "changed" | "neighbor"): GNode => {
    const r = rand();
    const kind = r < 0.27 ? "added" : r < 0.78 ? "functional" : r < 0.86 ? "signature" : r < 0.97 ? "text_only" : "deleted";
    const t = rand();
    const isChange = layer === "changed";
    return {
      id: `${path}::${name}`, label: name, kind: "function", path, start_line: line, end_line: line + 6 + Math.floor(rand() * 30),
      signature: `def ${name}(self, *args, **kwargs)`, layer: kind === "deleted" && isChange ? "ghost" : layer,
      change: isChange ? { kind, source: rand() < 0.08 ? "outside_session" : "session" } : null,
      test: isChange && !path.startsWith("tests/") ? { label: t < 0.3 ? "none" : t < 0.7 ? "direct" : "reached", count: t < 0.3 ? 0 : 1 + Math.floor(rand() * 4), nearest_tested: null } : null,
      callers_count: 0, callees_count: 0, parent: null, is_async: rand() < 0.2, is_public: !name.startsWith("_"), has_reason: false, finding_ids: [],
    };
  };

  for (const [dir, names] of Object.entries(FILES)) {
    for (const n of names) {
      const path = `${dir}/${n}${n.endsWith(".md") ? "" : ".py"}`;
      const count = 1 + Math.floor(rand() * (dir.startsWith("tests") ? 5 : 4));
      const used = new Set<string>();
      for (let i = 0; i < count; i++) {
        let name = dir.startsWith("tests") ? `test_${pick(NOUNS)}_${pick(VERBS)}` : `${pick(VERBS)}_${pick(NOUNS)}`;
        if (used.has(name)) name += `_${i}`;
        used.add(name);
        nodes.push(mk(path, name, 20 + i * 44, "changed"));
      }
    }
  }
  const changed = nodes.filter((n) => n.change);
  for (const path of NEIGHBOUR_FILES) for (let i = 0; i < 3; i++) nodes.push(mk(path, `${pick(VERBS)}_${pick(NOUNS)}_${i}`, 12 + i * 30, "neighbor"));
  const neighbours = nodes.filter((n) => n.layer === "neighbor");

  const edges: GEdge[] = [];
  const seen = new Set<string>();
  const add = (a: GNode, b: GNode) => {
    if (a.id === b.id || seen.has(a.id + ">" + b.id)) return;
    seen.add(a.id + ">" + b.id);
    const u = rand();
    edges.push({ id: `e${edges.length}`, source: a.id, target: b.id, kind: "CALLS", tier: u < 0.75 ? "EXTRACTED" : u < 0.93 ? "INFERRED" : "AMBIGUOUS", via: null });
    a.callees_count += 1; b.callers_count += 1;
  };
  const dirOf = (n: GNode) => n.path.split("/").slice(0, -1).join("/");
  for (const f of changed) {
    const calls = 1 + Math.floor(rand() * 2);
    for (let i = 0; i < calls; i++) {
      const r = rand();
      const pool = r < 0.25 ? changed.filter((x) => x.path === f.path) : r < 0.7 ? changed.filter((x) => dirOf(x) === dirOf(f)) : changed;
      add(f, pick(pool));
    }
    if (rand() < 0.22) { const nb = pick(neighbours); if (rand() < 0.5) add(f, nb); else add(nb, f); }
  }

  const reasons: AnalysisResponse["reasons"] = {};
  const findings: AnalysisResponse["findings"] = [];
  changed.filter(() => rand() < 0.3).forEach((n, i) => {
    n.has_reason = true;
    reasons[n.id] = {
      reason: pick(REASONS), driver: pick(["user_asked", "agent_decided", "not_stated"] as const), confidence: pick(["high", "medium"] as const),
      source: "session", history: [{ turn: `T${10 + i}`, text: `Edited ${n.label}` }], evidence: [{ turn: `T${3 + (i % 5)}`, quote: "Move everything onto the new transport base class." }],
    };
  });
  const untested = changed.filter((n) => n.change?.kind !== "deleted" && n.test?.label === "none");
  untested.slice(0, 3).forEach((n, i) => {
    n.finding_ids = [i + 1];
    findings.push({ id: i + 1, kind: "not_tested_after_change", finding: `${n.label} changed and no test reaches it`, functions: [n.id], evidence: [{ turn: "T40", quote: "All tests pass." }] });
  });

  const byChange: Record<string, number> = { added: 0, functional: 0, signature: 0, text_only: 0, deleted: 0 };
  for (const n of changed) byChange[n.change!.kind] += 1;
  const outside = changed.filter((n) => n.change?.source === "outside_session").length;

  return {
    ...base,
    analysis: { ...base.analysis, public_id: "large-demo", branch: "feature/transport-migration", short_sha: "9f3c1ab" },
    pull_request: base.pull_request && { ...base.pull_request, title: "Migrate every transport onto the shared base class" },
    banner: { kind: "partial_coverage", message: `${untested.length} changed functions have no test reaching them. ${outside} changed outside the session.` },
    summary: "Moves every transport onto one base class and updates the callers and tests.",
    stats: { functions_changed: changed.length, by_source: { session: changed.length - outside, session_then_formatted: 0, session_partial: 0, outside_session: outside }, by_change: byChange as AnalysisResponse["stats"]["by_change"], not_reached_by_tests: untested.length },
    graph: { nodes, edges, collapsed: [] },
    reading_order: changed.map((n) => n.id),
    impact: { summary: { functions: changed.length, files: new Set(changed.map((n) => n.path)).size, public_api: 0, uncertain_paths: 0 }, by_node: {} },
    // the agent worked through them in its own order, not alphabetical and not call order
    timeline: [...changed].sort(() => rand() - 0.5).filter((n) => !n.change || n.change.source === "session").map((n, i) => ({
      turn: `T${5 + i * 2}`, kind: "edit", ts: "2026-11-20T09:00:00Z", label: `Edit ${n.path.split("/").pop()}: ${n.label}`, nodes: [n.id], reverted: false, exit_code: null, finding_id: null,
    })),
    reasons, findings, diff_hunks: {},
  };
}
