import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { Bot, ExternalLink } from "lucide-react";
import { ApiError, fetchAnalysis, fetchTurns, type AnalysisResponse, type Driver, type GNode, type Reason, type Turn } from "../api";
import { Kpi, loginHref, PageHead, Panel } from "../ui";
import PrMode from "./PrMode";
import DiffFiles from "./DiffFiles";
import { DecisionStory, GovernancePanel, ReviewFindings, TimelinePanel } from "./PrSections";
// the graph brings in React Flow and its layout, so it loads when a PR page opens, not with the rest of the app
const GraphPanel = lazy(() => import("../graph/GraphPanel"));
import "../styles/prlive.css";

const short = (id: string) => id.split("::").slice(1).join("::") || id;

const DRIVER: Record<Driver, { label: string; who: "agent" | "human" }> = {
  user_asked: { label: "You asked", who: "human" },
  agent_decided: { label: "Agent decided", who: "agent" },
  not_stated: { label: "No reason in session", who: "agent" },
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

  if (st.k === "ok") return <Live a={st.a} />;
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
      {st.k === "error" && st.e.kind === "login" && <a className="btn primary" style={{ width: "fit-content" }} href={loginHref()}>Log in with GitHub</a>}
    </main>
  );
}

function Live({ a }: { a: AnalysisResponse }) {
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
  const linkedNodes = (t: string) => new Set(ids.filter((n) => timeline.some((e) => e.turn === t && e.nodes.includes(n)) || evTurns(n).has(t)));
  const hotNodes = turn ? linkedNodes(turn) : new Set([sel]);

  const shown = ids.filter((n) => lane === "all" ? true : lane === "untested" ? nodes[n]?.test?.label === "none" : reasons[n].driver === lane);
  const files = [...new Set(shown.map((n) => n.split("::")[0]))];
  const lastTest = facts.last_test_run;
  const bc = Object.entries(stats.by_change).filter(([, v]) => v > 0).map(([k, v]) => `${v} ${k.replace("_", " ")}`).join(" · ");
  const outside = stats.by_source.outside_session ?? 0;


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
          <a
            className="btn sm"
            href={a.pull_request?.url || (a.pull_request
              ? `https://github.com/${an.repo.owner}/${an.repo.name}/pull/${a.pull_request.number}`
              : `https://github.com/${an.repo.owner}/${an.repo.name}/pulls?q=${encodeURIComponent(`is:pr head:${an.branch}`)}`)}
            target="_blank"
            rel="noopener noreferrer"
          >
            View PR <ExternalLink size={13} />
          </a>
          <PrMode mode="live" />
        </>}
      />
      {a.banner && <div className={`lv-banner ${a.banner.kind}`}><b>{a.banner.kind.replace("_", " ")}.</b> {a.banner.message}</div>}

      <section className="kpis" aria-label="Summary">
        <Kpi value={stats.functions_changed} label="functions changed" sub={bc || "none"} />
        <Kpi value={`${stats.by_source.session ?? 0}/${stats.functions_changed}`} label="edited in the session" sub={outside ? `${outside} changed outside it` : "all inside the session"} tone={outside ? undefined : "ok"} />
        <Kpi value={stats.not_reached_by_tests} label="not reached by tests" sub="static estimate" tone={stats.not_reached_by_tests ? "bad" : "ok"} />
        <Kpi value={lastTest ? (lastTest.exit_code === 0 ? "Pass" : "Fail") : "None"} label="last test run" tone={lastTest ? (lastTest.exit_code === 0 ? "ok" : "bad") : undefined}
          sub={lastTest ? `${lastTest.turn} · ${lastTest.summary}${facts.tested_after_final_edit === false ? " · edits after it" : ""}` : "no test run in the session"} />
        <Kpi value={findings.length} label="review findings" tone={findings.length ? "bad" : "ok"} sub="checked against the session" />
      </section>

            {/* one selection for the whole page: the graph, the file diff, the decisions and the findings move together */}
      <Suspense fallback={<Panel title="What this change touched"><p className="lv-muted">Loading the graph…</p></Panel>}>
        <GraphPanel analysis={a} sel={sel || null} onSelect={(id) => { setTurn(null); setSel(id ?? ""); }} />
      </Suspense>

      <DiffFiles a={a} sel={sel || null} onSelect={(id) => { setTurn(null); setSel(id); }} />

      <GovernancePanel g={a.governance} nodes={nodes} sel={sel || null} onTurn={setTurn} onNode={(id) => { setTurn(null); setSel(id); }} />

      {findings.length > 0 && <ReviewFindings findings={findings} onTurn={setTurn} onFunction={(id) => { setTurn(null); setSel(id); }} />}

      <TimelinePanel timeline={timeline} selected={turn} onPick={(t) => setTurn(turn === t ? null : t)} />

      <div className="grid-7-5 lv-main">
        <div className="lv-col">
          <DecisionStory
            files={files}
            rowsOf={(f) => shown.filter((n) => n.split("::")[0] === f).map((n) => {
              const r = reasons[n], g = nodes[n];
              return { id: n, name: short(n), driver: r.driver, change: g?.change?.kind, untested: g?.test?.label === "none", reason: r.reason, turns: [...new Set(r.evidence.map((e) => e.turn))] };
            })}
            sel={sel || null} hot={hotNodes} lane={lane} onLane={setLane}
            onPick={(id) => { setTurn(null); setSel(id); }} />
        </div>

        {sel && reasons[sel] && (
          <Detail id={sel} r={reasons[sel]} g={nodes[sel]} hunks={a.diff_hunks[sel] ?? []}
            edits={timeline.filter((t) => t.nodes.includes(sel)).map((t) => t.turn)} />
        )}
      </div>

    </main>
  );
}

// The reasoning panel for the selected function: the few things a reader needs. Diff and history live in the sections above and below.
function Detail({ id, r, g, hunks, edits }: { id: string; r: Reason; g?: GNode; hunks: { patch: string }[]; edits: string[] }) {
  const who = DRIVER[r.driver];
  const quote = r.evidence[0];
  const tests = g?.test ? `${TESTS[g.test.label]}${g.test.count > 0 ? ` · ${g.test.count} test${g.test.count > 1 ? "s" : ""}` : ""}` : "not in the graph";
  return (
    <aside className="panel lv-detail" aria-label="Decision detail">
      <p className="ld-path">{id.split("::")[0]}{g?.start_line ? `:${g.start_line}` : ""}</p>
      <h3 className="ld-name">{short(id)}</h3>
      <div className="ld-tags">
        <span className="rv-tag">{who.label}</span>
        <span className="rv-tag">{r.confidence} confidence</span>
      </div>
      <section className="ld-sec">
        <p className="ld-label">Why</p>
        <p className="ld-why">{r.reason || "No reason given in the session."}</p>
        {quote && <p className="rv-quote"><span className="mono">{quote.turn}</span> <i>“{quote.quote}”</i></p>}
      </section>
      <section className="ld-sec">
        <p className="ld-line"><b>Tests</b> {tests}</p>
        {g && <p className="ld-line"><b>Blast radius</b> {g.callers_count} callers · {g.callees_count} callees</p>}
      </section>
      {edits.length > 0 && (
        <section className="ld-sec">
          <p className="ld-line"><b>Edited at</b> {edits.join(" · ")}</p>
        </section>
      )}
      {r.history.length > 0 && (
        <details className="gl-fold">
          <summary>How it got there · {r.history.length} step{r.history.length === 1 ? "" : "s"}</summary>
          <ol className="ld-hist">{r.history.map((h) => <li key={h.turn + h.text}><span className="mono">{h.turn}</span> {h.text}</li>)}</ol>
        </details>
      )}
      {hunks.length > 0 && (
        <details className="gl-fold">
          <summary>Diff · {hunks.length} hunk{hunks.length === 1 ? "" : "s"}</summary>
          <pre className="lv-diff">{hunks.flatMap((h) => h.patch.split("\n")).map((l, i) => <span key={i} className={l[0] === "+" ? "add" : l[0] === "-" ? "del" : l[0] === "@" ? "hh" : ""}>{l}{"\n"}</span>)}</pre>
        </details>
      )}
    </aside>
  );
}
