import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { Bot, Code2, User } from "lucide-react";
import { ApiError, fetchAnalysis, fetchTurns, type AnalysisResponse, type Driver, type GovDecision, type Governance, type GNode, type Reason, type TimelineItem, type Turn } from "../api";
import { TYPE_LABEL, type DType } from "../data";
import { Kpi, PageHead, Panel, Seg } from "../ui";
import PrMode from "./PrMode";
// the graph brings in React Flow and its layout, so it loads when a PR page opens, not with the rest of the app
const GraphPanel = lazy(() => import("../graph/GraphPanel"));
import "../styles/prlive.css";

const tnum = (t: string) => Number(t.replace(/\D/g, "")) || 0;
const hhmm = (ts?: string) => (ts ? ts.slice(11, 16) + " UTC" : "");
const base = (p: string) => p.split("/").pop() ?? p;
const short = (id: string) => id.split("::").slice(1).join("::") || id;

// The server does not classify decisions yet. This is a deterministic guess from the path and name only.
function inferType(path: string, name: string): DType {
  if (/(^|\/)(pyproject\.toml|requirements[^/]*\.txt|package\.json|go\.mod)$/.test(path)) return "dependency";
  if (/(^|\/)tests?\//.test(path) || /(^|\/)test_[^/]*$/.test(path)) return "test";
  if (/retry|backoff/i.test(path + name)) return "retries";
  return "design";
}

const DRIVER: Record<Driver, { label: string; who: "agent" | "human" }> = {
  user_asked: { label: "You asked", who: "human" },
  agent_decided: { label: "Agent decided", who: "agent" },
  not_stated: { label: "No reason in session", who: "agent" },
};
const SOURCE: Record<string, string> = {
  session: "Edited in this session", session_then_formatted: "Edited, then reformatted", session_partial: "Edited, then changed again outside",
  outside_session: "Changed outside the session",
};
const TESTS = { direct: "A test calls it directly", reached: "Reached by tests", reached_uncertain: "Reached only through uncertain paths", none: "No test reaches it" } as const;

type State = { k: "loading" } | { k: "error"; e: ApiError } | { k: "wait"; status: string } | { k: "failed"; msg: string } | { k: "ok"; a: AnalysisResponse; turns: Record<string, Turn> };

export default function PrLive({ id }: { id: string }) {
  const [st, setSt] = useState<State>({ k: "loading" });
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        // demo ids render the contract fixture, so the PR tab can be tried without an analysis in the database
        if (id === "demo" || id === "demo-large") {
          const [{ default: fixture }, { makeLarge }] = await Promise.all([import("../../../contract/fixtures/analysis_graph_rich.json"), import("../graph/large")]);
          // the contract fixture predates the governance block; an unavailable one makes the panel say so
          const base: AnalysisResponse = { ...(fixture as unknown as Omit<AnalysisResponse, "governance">), governance: { decisions: [], highlights: [], flags: [], tool_stats: {}, attempts: 0, human_interventions: 0, steering_files: [], steering_rules: 0, available: false } };
          if (alive) setSt({ k: "ok", a: id === "demo" ? base : makeLarge(base), turns: {} });
          return;
        }
        const a = await fetchAnalysis(id);
        if (!alive) return;
        const status = a.analysis.status;
        if (status === "queued" || status === "running") { setSt({ k: "wait", status }); timer = setTimeout(load, 3000); return; }
        if (status === "failed") { setSt({ k: "failed", msg: `${a.analysis.error_code ?? "failed"}: ${a.analysis.error_message ?? ""}` }); return; }
        // ponytail: one turns call, capped at the API's 50 ids; page the ids if a session ever needs more
        const ids = new Set<string>(a.timeline.filter((t) => t.kind === "user_request").map((t) => t.turn));
        Object.values(a.reasons).forEach((r) => { r.evidence.forEach((e) => ids.add(e.turn)); r.history.forEach((h) => ids.add(h.turn)); });
        a.findings.forEach((f) => f.evidence.forEach((e) => ids.add(e.turn)));
        const t = ids.size ? await fetchTurns(id, [...ids].slice(0, 50)).catch(() => ({ turns: [] as Turn[] })) : { turns: [] as Turn[] };
        if (alive) setSt({ k: "ok", a, turns: Object.fromEntries(t.turns.map((x) => [x.turn_id, x])) });
      } catch (e) {
        if (alive) setSt({ k: "error", e: e instanceof ApiError ? e : new ApiError("server", String(e)) });
      }
    }
    load();
    return () => { alive = false; clearTimeout(timer); };
  }, [id]);

  if (st.k === "ok") return <Live a={st.a} turns={st.turns} />;
  const msg =
    st.k === "loading" ? "Loading the analysis…" :
    st.k === "wait" ? `The analysis is ${st.status}. This page refreshes on its own.` :
    st.k === "failed" ? `The analysis failed. ${st.msg}` :
    st.e.kind === "login" ? "You are not logged in. Log in with GitHub, or run the API with DEV_VIEWER_LOGIN for local work." :
    st.e.kind === "notfound" ? `No analysis with id ${id}.` : st.e.message;
  return (
    <main className="wrap page">
      <PageHead title="PR analysis" sub={msg} meta={<><span className="chip sim">{id}</span><PrMode mode="live" /></>} />
      {st.k === "error" && st.e.kind === "notfound" && <p className="lv-muted">Try the demo: <a href="#/pr/demo">small commit</a> · <a href="#/pr/demo-large">large commit</a></p>}
      {st.k === "error" && st.e.kind === "login" && <a className="btn primary" style={{ width: "fit-content" }} href="/auth/login">Log in with GitHub</a>}
    </main>
  );
}

function Live({ a, turns }: { a: AnalysisResponse; turns: Record<string, Turn> }) {
  const { analysis: an, stats, facts, timeline, reasons, findings } = a;
  const nodes = useMemo(() => Object.fromEntries(a.graph.nodes.map((n) => [n.id, n])) as Record<string, GNode>, [a]);
  const ids = useMemo(() => {
    const order = a.reading_order.filter((x) => reasons[x]);
    return [...order, ...Object.keys(reasons).filter((x) => !order.includes(x))];
  }, [a, reasons]);
  const [sel, setSel] = useState(ids[0] ?? "");
  const [turn, setTurn] = useState<string | null>(null);
  const [lane, setLane] = useState<"all" | Driver | "untested">("all");

  const evTurns = (n: string) => new Set([...(reasons[n]?.evidence ?? []).map((e) => e.turn), ...(reasons[n]?.history ?? []).map((h) => h.turn)]);
  const linkedEvents = (n: string) => new Set(timeline.filter((t) => t.nodes.includes(n) || evTurns(n).has(t.turn)).map((t) => t.turn));
  const linkedNodes = (t: string) => new Set(ids.filter((n) => timeline.some((e) => e.turn === t && e.nodes.includes(n)) || evTurns(n).has(t)));
  const hotEvents = turn ? new Set([turn]) : linkedEvents(sel);
  const hotNodes = turn ? linkedNodes(turn) : new Set([sel]);

  const shown = ids.filter((n) => lane === "all" ? true : lane === "untested" ? nodes[n]?.test?.label === "none" : reasons[n].driver === lane);
  const files = [...new Set(shown.map((n) => n.split("::")[0]))];
  const nums = [...timeline.map((t) => tnum(t.turn)), ...ids.flatMap((n) => [...evTurns(n)].map(tnum))];
  const lo = Math.min(...nums), hi = Math.max(...nums);
  const pos = (t: string) => (hi === lo ? 0.5 : (tnum(t) - lo) / (hi - lo));
  const lastTest = facts.last_test_run;
  const bc = Object.entries(stats.by_change).filter(([, v]) => v > 0).map(([k, v]) => `${v} ${k.replace("_", " ")}`).join(" · ");
  const outside = stats.by_source.outside_session ?? 0;

  // an arc only where a human turn is followed by a reverted edit; the server sends no such data today
  const arcs = timeline.filter((e) => e.reverted).flatMap((e) => {
    const u = [...timeline].reverse().find((x) => x.kind === "user_request" && tnum(x.turn) < tnum(e.turn));
    return u ? [{ from: u.turn, to: e.turn }] : [];
  });

  return (
    <main className="wrap page">
      <PageHead
        crumbs={<>{an.repo.owner}/{an.repo.name} <b>›</b> {an.branch} <b>›</b> <span>{an.short_sha}</span></>}
        title={a.pull_request?.title ?? `${an.branch} @ ${an.short_sha}`}
        sub={a.summary}
        meta={<>
          <span className="chip agent"><Bot size={12} /> {an.agent ?? "agent"}</span>
          {an.llm_model && <span className="chip">{an.llm_model}</span>}
          <span className="chip">{a.pull_request ? `PR #${a.pull_request.number} · ${a.pull_request.state}` : "No PR yet"}</span>
          <span className="chip ok">Live data · {an.public_id}</span>
          <PrMode mode="live" />
        </>}
      />
      {a.banner && <div className={`lv-banner ${a.banner.kind}`}><b>{a.banner.kind.replace("_", " ")}.</b> {a.banner.message}</div>}

      <section className="kpis" aria-label="Summary">
        <Kpi value={stats.functions_changed} label="functions changed" sub={bc || "none"} />
        <Kpi value={`${stats.by_source.session ?? 0}/${stats.functions_changed}`} label="edited in the session" sub={outside ? `${outside} changed outside it` : "all inside the session"} tone={outside ? undefined : "ok"} />
        <Kpi value={stats.not_reached_by_tests} label="not reached by tests" sub="static estimate, not measured" tone={stats.not_reached_by_tests ? "bad" : "ok"} />
        <Kpi value={lastTest ? (lastTest.exit_code === 0 ? "Pass" : "Fail") : "None"} label="last test run" tone={lastTest ? (lastTest.exit_code === 0 ? "ok" : "bad") : undefined}
          sub={lastTest ? `${lastTest.turn} · ${lastTest.summary}${facts.tested_after_final_edit === false ? " · edits after it" : ""}` : "no test run in the session"} />
        <Kpi value={findings.length} label="review findings" tone={findings.length ? "bad" : "ok"} sub="checked against the session" />
      </section>

      <Suspense fallback={<Panel title="What this change touched"><p className="lv-muted">Loading the graph…</p></Panel>}><GraphPanel analysis={a} /></Suspense>

      <GovernancePanel g={a.governance} onTurn={setTurn} />

      <Panel title="Review findings" sub={findings.length ? `${findings.length} · each backed by a quoted turn` : undefined}>
        {findings.length === 0 ? <p className="lv-muted">No review findings.</p> : (
          <ul className="lv-findings">
            {findings.map((f) => (
              <li key={f.id}>
                <span className="chip bad">{f.kind.replace(/_/g, " ")}</span>
                <div><b>{f.finding}</b>
                  {f.evidence.map((e) => <small key={e.turn + e.quote}><button className="lv-link" onClick={() => setTurn(e.turn)}>{e.turn}</button> “{e.quote}”</small>)}
                </div>
                {f.functions[0] && <button className="lv-link" onClick={() => { setTurn(null); setSel(f.functions[0]); }}>{short(f.functions[0])}</button>}
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <div className="grid-7-5 lv-main">
        <div className="lv-col">
          <Panel title="Session timeline" sub={`${timeline.length} events · turns T${lo}–T${hi} · click one to see what it touched`}>
            <div className="lv-tl">
              <span className="lv-lane a">Agent</span><span className="lv-lane h">You</span>
              <i className="lv-axis" aria-hidden="true" />
              {timeline.map((e, i) => <Ev key={e.turn} e={e} i={i} p={pos(e.turn)} hot={hotEvents.has(e.turn)} on={turn === e.turn} onClick={() => setTurn(turn === e.turn ? null : e.turn)} />)}
              {arcs.length > 0 && <span className="lv-arcs">{arcs.length} human turn{arcs.length > 1 ? "s" : ""} followed by a reverted edit</span>}
            </div>
            <p className="lv-note">A red diamond on the human side is a tool call you denied. Overrule arcs appear where a reverted edit follows a human turn.</p>
          </Panel>

          <Panel title="Decision story" sub="one per changed function · type inferred from path, model classification not built yet"
            aside={<Seg value={lane} onChange={setLane} options={[
              { id: "all", label: "All" }, { id: "user_asked", label: "You asked" }, { id: "agent_decided", label: "Agent" },
              { id: "not_stated", label: "No reason" }, { id: "untested", label: "Untested" }]} />}>
            <div className="lv-lanes-h"><span className="a"><Bot size={13} /> Agent decided</span><span className="h"><User size={13} /> You asked</span></div>
            {files.length === 0 && <p className="lv-muted">Nothing matches this filter.</p>}
            {files.map((f) => (
              <div key={f} className="lv-file">
                <div className="lv-file-h mono">{f}</div>
                <div className="lv-cards">
                  {shown.filter((n) => n.split("::")[0] === f).map((n) => {
                    const r = reasons[n], g = nodes[n], t = inferType(f, short(n));
                    return (
                      <button key={n} className={`lv-card ${r.driver === "user_asked" ? "h" : "a"} ${r.driver === "not_stated" ? "ns" : ""} t-${t} ${hotNodes.has(n) ? "hot" : ""} ${sel === n ? "sel" : ""}`}
                        onClick={() => { setTurn(null); setSel(n); }} aria-pressed={sel === n}>
                        <span className="lv-card-t"><i />{short(n)}</span>
                        <span className="lv-card-m">
                          {g?.change && <span className="chip">{g.change.kind}</span>}
                          {g?.test?.label === "none" && <span className="chip bad">untested</span>}
                          {r.driver === "not_stated" && <span className="chip warn">no reason</span>}
                          <span className="mono">{[...new Set(r.evidence.map((e) => e.turn))].join(" ") || "—"}</span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </Panel>
        </div>

        {sel && reasons[sel] && <Detail a={a} id={sel} r={reasons[sel]} g={nodes[sel]} turns={turns} />}
      </div>

      <details className="panel lv-todo">
        <summary>Not computed yet <span className="lv-muted">· things the server does not produce today</span></summary>
        <ul>
          <li><b>Acceptance criteria and iterations.</b> No criteria are extracted from prompts or tickets, so no ladders and no "agent missed it / requirement thin" verdict.</li>
          <li><b>Function decision types.</b> The type chips on the function cards are inferred from file paths. The Governance panel above has model-classified types.</li>
        </ul>
        <a className="lv-link" href="#/pr/mock">See how these look on the mock page</a>
      </details>
    </main>
  );
}

const KIND_LABEL: Record<string, string> = {
  choice: "Agent choice", redirect: "Redirected", reject: "Rejected", requirement: "Added requirement",
  discussion: "Chose in discussion", permission_denied: "Denied tool call",
};
const FLAG_LABEL: Record<string, string> = {
  "new-dependency": "New dependency", "skipped-test": "Skipped test", unsupported: "Unsupported claim", "async-gap": "Async gap",
};

function GovernancePanel({ g, onTurn }: { g: Governance; onTurn: (t: string) => void }) {
  if (!g.available) {
    return (
      <Panel title="Governance" sub="decisions, human interventions and steering">
        <p className="lv-muted">No governance data for this push. It needs an agent session.</p>
      </Panel>
    );
  }
  const human = g.decisions.filter((d) => d.actor === "human");
  const agent = g.decisions.filter((d) => d.actor === "agent");
  const tools = Object.entries(g.tool_stats).sort((x, y) => y[1].calls - x[1].calls);
  const row = (d: GovDecision) => (
    <li key={d.turn + d.kind + d.quote.slice(0, 12)}>
      <span className={`chip ${d.actor === "human" ? "warn" : "agent"}`}>{d.actor === "human" ? <User size={11} /> : <Bot size={11} />} {KIND_LABEL[d.kind] ?? d.kind}</span>
      <div>
        <b>{d.choice || d.proposal}</b>
        {d.proposal && d.choice && <small>{d.proposal}</small>}
        {d.quote && <small><button className="lv-link" onClick={() => onTurn(d.turn)}>{d.turn}</button> “{d.quote}”</small>}
        {d.rule && <small>Rule: {d.rule} {d.rule_followed === true && <span className="chip ok">followed</span>}{d.rule_followed === false && <span className="chip bad">not followed</span>}</small>}
      </div>
      <span className="chip">{d.type}</span>
    </li>
  );
  return (
    <Panel title="Governance" sub={`${g.decisions.length} decisions · ${g.human_interventions} human interventions · ${g.attempts} attempt${g.attempts === 1 ? "" : "s"} · ${g.steering_rules} steering rules read from ${g.steering_files.length ? g.steering_files.join(", ") : "no steering files"}`}>
      {g.flags.length > 0 && (
        <div className="gv-chips" style={{ marginBottom: 12 }}>
          {g.flags.map((f) => <span key={f.flag + f.path} className="chip bad" title={f.detail}>{FLAG_LABEL[f.flag] ?? f.flag}{f.path ? ` · ${base(f.path)}` : ""}</span>)}
        </div>
      )}
      {g.highlights.length > 0 && (
        <ul className="lv-findings" style={{ marginBottom: 12 }}>
          {g.highlights.map((h) => (
            <li key={h.turn + h.text}>
              <span className={`chip ${h.kind === "went_right" ? "ok" : "bad"}`}>{h.kind === "went_right" ? "Went right" : "Went wrong"}</span>
              <div><b>{h.text}</b>{h.quote && <small><button className="lv-link" onClick={() => onTurn(h.turn)}>{h.turn}</button> “{h.quote}”</small>}</div>
            </li>
          ))}
        </ul>
      )}
      {human.length === 0 && agent.length === 0 && <p className="lv-muted">No decisions were found in this session.</p>}
      {human.length > 0 && <><h4 className="lv-muted" style={{ margin: "8px 0" }}>Where a person stepped in</h4><ul className="lv-findings">{human.map(row)}</ul></>}
      {agent.length > 0 && <><h4 className="lv-muted" style={{ margin: "12px 0 8px" }}>What the agent decided</h4><ul className="lv-findings">{agent.map(row)}</ul></>}
      {tools.length > 0 && <p className="lv-note">Tools: {tools.map(([n, t]) => `${n} ×${t.calls}${t.tokens ? ` (${t.tokens.toLocaleString()} tok)` : ""}`).join(" · ")}</p>}
    </Panel>
  );
}

function Ev({ e, i, p, hot, on, onClick }: { e: TimelineItem; i: number; p: number; hot: boolean; on: boolean; onClick: () => void }) {
  const user = e.kind === "user_request" || e.kind === "denied";
  const cls = e.kind === "denied" ? "denied" : user ? "user" : e.kind === "test_run" ? (e.exit_code === 0 ? "pass" : "fail") : e.reverted ? "revert" : "edit";
  const label = e.kind === "edit" ? base(e.label) : e.label.length > 38 ? e.label.slice(0, 38) + "…" : e.label;
  return (
    <button className={`lv-ev ${cls} ${user ? "below" : "above"} s${i % 2} ${hot ? "hot" : ""} ${on ? "on" : ""}`} style={{ ["--p" as string]: p }} onClick={onClick}
      title={`${e.turn} · ${hhmm(e.ts)} · ${e.label}`}>
      <span className="lv-l"><b className="mono">{e.turn}</b> {label}</span><i className="lv-m" />
    </button>
  );
}

function Detail({ a, id, r, g, turns }: { a: AnalysisResponse; id: string; r: Reason; g?: GNode; turns: Record<string, Turn> }) {
  const type = inferType(id.split("::")[0], short(id));
  const hunks = a.diff_hunks[id] ?? [];
  const callers = a.impact.by_node[id] ?? [];
  const edits = a.timeline.filter((t) => t.nodes.includes(id));
  const who = (t: string) => ({ user: "You said", assistant: "Agent said", thought: "Agent thought", edit: "Agent edit", shell: "Agent ran" } as Record<string, string>)[turns[t]?.kind] ?? "Turn";
  return (
    <aside className="panel lv-detail" aria-label="Decision detail">
      <div className="lv-chips">
        <span className={`chip ${DRIVER[r.driver].who}`}>{DRIVER[r.driver].who === "agent" ? <Bot size={12} /> : <User size={12} />}{DRIVER[r.driver].label}</span>
        <span className={`chip t-${type}`}><i />{TYPE_LABEL[type]} · inferred</span>
        <span className={`chip ${r.confidence === "high" ? "ok" : r.confidence === "low" ? "warn" : ""}`}>{r.confidence} confidence</span>
        {g?.change && <span className="chip">{g.change.kind}</span>}
      </div>
      <h3 className="lv-h">{short(id)}</h3>
      <div className="lv-code mono"><Code2 size={13} /> {id.split("::")[0]}{g?.start_line ? `:${g.start_line}–${g.end_line}` : ""}</div>
      {g?.signature && <pre className="lv-sig">{g.signature}</pre>}

      <div className="lv-sec">
        <span className="eyebrow">{r.driver === "agent_decided" ? "Agent's stated rationale · unverified" : r.driver === "user_asked" ? "Why, from your request" : "Reason"}</span>
        <p>{r.reason || "No reason given in the session."}</p>
        <small className="lv-muted">{SOURCE[r.source] ?? r.source}</small>
      </div>

      {r.evidence.length > 0 && <div className="lv-sec"><span className="eyebrow">Evidence · quoted from the session</span>
        {r.evidence.map((e) => (
          <blockquote key={e.turn + e.quote} className={turns[e.turn]?.kind === "user" ? "u" : "g"}>
            <small className="mono">{who(e.turn)} · {e.turn}{turns[e.turn] ? ` · ${hhmm(turns[e.turn].ts)}` : ""}</small>“{e.quote}”
          </blockquote>))}
      </div>}
      {r.history.length > 0 && <div className="lv-sec"><span className="eyebrow">How it got there</span>
        <ol className="lv-hist">{r.history.map((h) => <li key={h.turn + h.text}><span className="mono">{h.turn}</span>{h.text}</li>)}</ol></div>}

      <div className="lv-sec"><span className="eyebrow">Tests · static estimate</span>
        <p><span className={`chip ${g?.test?.label === "none" ? "bad" : g?.test ? "ok" : ""}`}>{g?.test ? TESTS[g.test.label] : "not in the graph view"}</span>
          {g?.test && g.test.count > 0 && <span className="lv-muted"> {g.test.count} test{g.test.count > 1 ? "s" : ""}</span>}</p>
        {g?.test?.nearest_tested && <small className="lv-muted">Nearest tested function: {short(g.test.nearest_tested)}</small>}
      </div>
      {g && <div className="lv-sec"><span className="eyebrow">Blast radius</span>
        <p>{g.callers_count} direct caller{g.callers_count === 1 ? "" : "s"} · {g.callees_count} callee{g.callees_count === 1 ? "" : "s"}{callers.length ? ` · ${callers.length} upstream within ${Math.max(...callers.map((c) => c.depth))} hops` : ""}</p>
        {callers.slice(0, 4).map((c) => <small key={c.id} className="lv-muted mono">{"↑".repeat(c.depth)} {short(c.id)}{c.uncertain ? " (uncertain)" : ""}</small>)}
      </div>}
      {edits.length > 0 && <div className="lv-sec"><span className="eyebrow">Session edits that touched it</span>
        <p>{edits.map((e) => <span key={e.turn} className="chip lv-tag">{e.turn} · {hhmm(e.ts)}</span>)}</p></div>}
      {hunks.length > 0 && <div className="lv-sec"><span className="eyebrow">Diff</span>
        <pre className="lv-diff">{hunks.flatMap((h) => h.patch.split("\n")).map((l, i) => <span key={i} className={l[0] === "+" ? "add" : l[0] === "-" ? "del" : l[0] === "@" ? "hh" : ""}>{l}{"\n"}</span>)}</pre></div>}
    </aside>
  );
}
