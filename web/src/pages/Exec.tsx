import { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import { TYPE_LABEL, type DType } from "../data";
import { type Autonomy, type ExecData, type Period, type Source } from "../api";
import { useExec } from "../queries";
import { shortDay } from "../format";
import { DataGate, Kpi, PageHead, Panel, Seg, TypeChip } from "../ui";
import "../styles/exec.css";

const TYPE_ORDER: DType[] = ["architecture", "design", "dependency", "retries", "test", "scope"];

// Charts draw at their real pixel width so text stays at the type scale on phones.
function useWidth(): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(640);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((e) => setW(Math.max(260, Math.floor(e[0].contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

const Link = ({ href, children }: { href: string; children: React.ReactNode }) => (
  <a className="btn sm" href={href}>{children} <ArrowRight size={14} /></a>
);


function Trend({ d }: { d: ExecData }) {
  const [ref, w] = useWidth();
  const H = 244, L = 34, R = 44, T = 32, B = 26;
  const a = d.adherence, o = d.repeat_overrides, labels = d.weeks.map(shortDay);
  const n = a.length;
  const aVals = a.filter((v): v is number => v !== null);
  const oVals = o.filter((v): v is number => v !== null);
  const aMin = aVals.length ? Math.min(60, Math.floor(Math.min(...aVals) / 10) * 10) : 60;
  const oMax = Math.max(14, Math.ceil((oVals.length ? Math.max(...oVals) : 0) / 7) * 7);
  // draw only the weeks that have a value (from the first to the last), so the points are not lost in empty weeks
  const measured = a.map((v, i) => (v !== null || o[i] !== null ? i : -1)).filter((i) => i >= 0);
  const i0 = measured.length ? measured[0] : 0, i1 = measured.length ? measured[measured.length - 1] : Math.max(0, n - 1);
  const x = (i: number) => (i1 === i0 ? L + (w - L - R) / 2 : L + ((i - i0) * (w - L - R)) / (i1 - i0));
  const xTicks = [...new Set([i0, ...(i1 - i0 >= 4 ? [Math.round((i0 + i1) / 2)] : []), i1])];
  const ya = (v: number) => T + ((100 - v) / Math.max(1, 100 - aMin)) * (H - T - B);
  const yo = (v: number) => T + ((oMax - v) / Math.max(1, oMax)) * (H - T - B);
  const aTicks = [aMin, Math.round((aMin + 100) / 2), 100];
  const oTicks = [0, Math.round(oMax / 2), oMax];
  // a week with no value (null) leaves a gap in the line instead of a zero
  const path = (vs: (number | null)[], y: (v: number) => number) => {
    let pen = false;
    return vs.map((v, i) => { if (v === null) { pen = false; return ""; } const s = `${pen ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`; pen = true; return s; }).filter(Boolean).join(" ");
  };
  const lastOf = (vs: (number | null)[]) => { for (let i = vs.length - 1; i >= 0; i--) if (vs[i] !== null) return i; return -1; };
  const la = lastOf(a), lo = lastOf(o);
  return (
    <div ref={ref} className="chart">
      <svg width={w} height={H} role="img" aria-label="Skill adherence and repeat-override rate by week, with policy publish dates">
        {aTicks.map((v) => (
          <g key={v}>
            <line x1={L} x2={w - R} y1={ya(v)} y2={ya(v)} className="grid" />
            <text x={L - 8} y={ya(v) + 4} textAnchor="end" className="ax">{v}%</text>
          </g>
        ))}
        {oTicks.map((v) => <text key={v} x={w - R + 8} y={yo(v) + 4} className="ax human">{v}</text>)}
        {d.policy_events.map((e) => (
          <g key={e.id}>
            <line x1={x(e.week)} x2={x(e.week)} y1={T - 6} y2={H - B} className="event" />
            <text x={x(e.week)} y={T - 12} textAnchor={x(e.week) < 70 ? "start" : x(e.week) > w - 90 ? "end" : "middle"} className="ev-t">{e.id}{w >= 520 ? " published" : ""}</text>
          </g>
        ))}
        <path d={path(a, ya)} className="line agent" />
        <path d={path(o, yo)} className="line human" />
        {a.map((v, i) => v !== null && <circle key={i} cx={x(i)} cy={ya(v)} r={i === la ? 6 : 4} className="pt agent"><title>{labels[i]}: {v}% adherence</title></circle>)}
        {o.map((v, i) => v !== null && <circle key={i} cx={x(i)} cy={yo(v)} r={i === lo ? 6 : 4} className="pt human"><title>{labels[i]}: {v} repeat overrides per 100 sessions</title></circle>)}
        {la >= 0 && <text x={Math.min(x(la) + 10, w - 36)} y={ya(a[la]!) - 8} className="end agent">{a[la]}%</text>}
        {lo >= 0 && <text x={Math.min(x(lo) + 10, w - 36)} y={yo(o[lo]!) + 16} className="end human">{o[lo]}</text>}
        {n === 0 && <text x={w / 2} y={H / 2} textAnchor="middle" className="ax">No weeks to show</text>}
        {xTicks.map((i) => (
          <text key={i} x={x(i)} y={H - 6} textAnchor={i1 === i0 ? "middle" : i === i0 ? "start" : i === i1 ? "end" : "middle"} className="ax">{labels[i]}</text>
        ))}
      </svg>
      <p className="legend-row">
        <span><i className="sw agent" />Skill adherence, % of agent decisions</span>
        <span><i className="sw human" />Repeat overrides per 100 sessions</span>
        <span className="mono dim">{d.period === "30d" ? "last 5 weeks" : "last 12 weeks"}{i1 === i0 && n > 1 ? ` · measured from ${labels[i0]} only` : ""}</span>
      </p>
    </div>
  );
}

function Mix({ d }: { d: ExecData }) {
  const [ref, w] = useWidth();
  const H = w > 560 ? 290 : 200, L = 30, T = 8, B = 22;
  const weeks = d.weeks.length;
  const totals = Array.from({ length: weeks }, (_, i) => TYPE_ORDER.reduce((s, t) => s + d.mix[t][i], 0));
  // Scale to the data (a fixed 40 made a handful of decisions look like empty space); three ticks: 0, half, top.
  const peak = Math.max(4, ...totals);
  const max = Math.ceil(peak / 4) * 4;
  const ticks = [0, Math.round(max / 2), max];
  const slot = (w - L) / weeks, bw = Math.min(28, slot * 0.64);
  const y = (v: number) => T + (1 - v / max) * (H - T - B);
  return (
    <div ref={ref} className="chart">
      <svg width={w} height={H} role="img" aria-label="Decisions per week by type">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={L} x2={w} y1={y(v)} y2={y(v)} className="grid" />
            <text x={L - 8} y={y(v) + 4} textAnchor="end" className="ax">{v}</text>
          </g>
        ))}
        {Array.from({ length: weeks }, (_, i) => {
          let acc = 0;
          const cx = L + slot * i + (slot - bw) / 2;
          return (
            <g key={i}>
              {TYPE_ORDER.map((t) => {
                const v = d.mix[t][i];
                const h = Math.max(0, y(acc) - y(acc + v) - 1);
                const r = h > 0 ? <rect key={t} x={cx} y={y(acc + v)} width={bw} height={h} rx="2" style={{ fill: `var(--t-${t})` }}><title>{shortDay(d.weeks[i])} · {TYPE_LABEL[t]}: {v}</title></rect> : null;
                acc += v;
                return r;
              })}
              {totals[i] > 0 && <text x={cx + bw / 2} y={y(totals[i]) - 5} textAnchor="middle" className="ax total">{totals[i]}</text>}
              {(weeks < 8 || i % 2 === 0) && <text x={cx + bw / 2} y={H - 6} textAnchor="middle" className="ax">{shortDay(d.weeks[i])}</text>}
            </g>
          );
        })}
      </svg>
      <div className="chips">{TYPE_ORDER.map((t) => <TypeChip key={t} t={t} />)}</div>
    </div>
  );
}

const AUTONOMY: Record<Autonomy, { cls: string; text: string }> = {
  advice: { cls: "ok", text: "Advice" },
  check: { cls: "warn", text: "PR check" },
  gate: { cls: "bad", text: "Hard gate" },
};

const Meter = ({ v, bad }: { v: number; bad?: boolean }) => (
  <span className="meter"><span className="track"><i className={bad ? "bad" : ""} style={{ width: `${v}%` }} /></span><b className="mono">{v}%</b></span>
);

function ExecBody({ d }: { d: ExecData }) {
  const k = d.kpis;
  const decided = TYPE_ORDER.reduce((s, t) => s + d.mix[t].reduce((a, v) => a + v, 0), 0);
  const humanShare = decided ? Math.round((d.human_per_week.reduce((s, v) => s + v, 0) / decided) * 100) : 0;

  const r = d.rework;
  const total = r.first + r.missed + r.thin;
  const pct = (v: number) => (total ? Math.round((v / total) * 100) : 0);
  const thinOfRework = r.missed + r.thin ? Math.round((r.thin / (r.missed + r.thin)) * 100) : 0;
  const unit = d.sources.rework === "measured" ? "sessions" : "acceptance criteria";
  const mixed = Object.values(d.sources).includes("measured");
  // when the page mixes measured and sample sections, each sample one says so
  const src = (s: Source) => (mixed && s === "sample" ? <span className="chip sim">Sample data</span> : undefined);
  const n = (v: number | null, f: (x: number) => string = String) => (v === null ? "n/a" : f(v));
  const headline = d.headline;

  return (
    <>
      <section className="kpis five" aria-label="Summary">
        <Kpi tone="ok" value={n(k.adherence.v, (x) => `${x}%`)} label="Skill adherence" />
        <Kpi tone="hot" value={n(k.override.v, (x) => x.toFixed(1))} label="Repeat overrides per 100 sessions" />
        <Kpi value={n(k.verified.v, (x) => `${x}%`)} label="Claims verified by code" />
        <Kpi value={n(k.unrequested.v, (x) => `${x}%`)} label="Changes nobody asked for" />
        <Kpi value={k.pending.v} label="Policies waiting for approval" sub={<>oldest {k.pending.oldest_days} days</>} />
      </section>

      {d.measured && d.measured.sessions > 0 && (
        <Panel title="Live from your sessions" sub={d.sources.trend === "measured" ? "Measured by Unpack from real agent sessions, over all time. The charts below use the sessions in this period." : "Measured by Unpack from real agent sessions. The charts below are the sample baseline."}
          aside={<span className="chip ok">Measured</span>}>
          <section className="kpis" aria-label="Measured">
            <Kpi value={d.measured.sessions} label="sessions analysed" sub={`${d.measured.decisions} decisions found`} />
            <Kpi value={d.measured.human_decisions} label="human interventions" sub={Object.entries(d.measured.human_kinds).map(([k, v]) => `${v} ${k.replace("_", " ")}`).join(" · ") || "none"} tone="hot" />
            <Kpi value={d.measured.adherence === null ? "n/a" : `${d.measured.adherence}%`} label="steering followed" sub={`${d.measured.rule_checks} decisions checked against a rule`} tone="ok" />
            <Kpi value={d.measured.tool_calls} label="tool calls" sub={`${d.measured.tokens.toLocaleString()} tokens`} />
            <Kpi value={Object.values(d.measured.flags).reduce((a, b) => a + b, 0)} label="flags raised" sub={Object.entries(d.measured.flags).map(([k, v]) => `${v} ${k}`).join(" · ") || "none"} tone="bad" />
          </section>
        </Panel>
      )}

      <Panel
        title="Is governance working?"
        sub={headline
          ? `Repeat overrides ${headline.before} → ${headline.after} per 100 sessions since ${headline.id} was published. Associated with the policy, not proven caused by it.`
          : "Associated with the policy, not proven caused by it."}
        aside={<>{src(d.sources.trend)} <Link href="#/govern">Policies</Link></>}
      >
        <Trend d={d} />
      </Panel>

      <div className="grid-7-5">
        <Panel title="What agents and people decide" sub="decisions per week, by type" aside={<>{src(d.sources.trend)} <Link href="#/pr">Example PR</Link></>}>
          <Mix d={d} />
          <div className="share">
            <div className="share-bar" role="img" aria-label={`Agent decided ${100 - humanShare}%, human decided ${humanShare}%`}>
              {100 - humanShare > 0 && <i className="agent" style={{ width: `${100 - humanShare}%` }}><span className="w">Agent&nbsp;</span>{100 - humanShare}%</i>}
              {humanShare > 0 && <i className="human" style={{ width: `${humanShare}%` }}><span className="w">Human&nbsp;</span>{humanShare}%</i>}
            </div>
            {(humanShare === 0 || humanShare === 100) && <p className="legend-row">Agent {100 - humanShare}% · Human {humanShare}%</p>}
          </div>
        </Panel>

        <div className="stackcol">
        <Panel title="Why criteria needed rework" sub={`${total} ${unit}`} aside={<>{src(d.sources.rework)} <Link href="#/team">Teams</Link></>}>
          <div className="stack" role="img" aria-label="Criteria met first try, missed by the agent, or requirement too thin">
            <i className="ok" style={{ width: `${pct(r.first)}%` }} />
            <i className="agent" style={{ width: `${pct(r.missed)}%` }} />
            <i className="warn" style={{ width: `${pct(r.thin)}%` }} />
          </div>
          <ul className="legend-list">
            <li><i className="sw ok" /><span>Met on the first try</span><b className="mono">{pct(r.first)}%</b></li>
            <li><i className="sw agent" /><span>Agent missed a clear requirement</span><b className="mono">{pct(r.missed)}%</b></li>
            <li><i className="sw warn" /><span>Requirement was thin</span><b className="mono">{pct(r.thin)}%</b></li>
          </ul>
          <p className="note">
            <b>Requirement was thin in {thinOfRework}% of reworked criteria.</b> Fix the brief, not the agent. Cause is proposed by the model and confirmed by a reviewer.
          </p>
        </Panel>
        <Panel title="Where human decisions come from" sub="share of human decisions, by how they entered the record" aside={src(d.sources.human_kinds)}>
          {d.human_kinds.length === 0 ? (
            <p className="panel-sub">No human interventions recorded in this period yet.</p>
          ) : (
            <ul className="kinds">
              {d.human_kinds.map((h) => (
                <li key={h.kind}><span>{h.label}</span><span className="track"><i style={{ width: `${Math.min(100, h.pct)}%` }} /></span><b className="mono">{h.pct}%</b></li>
              ))}
            </ul>
          )}
        </Panel>
        </div>
      </div>

      <div className="grid-7-5">
        <Panel
          title="Where agents are trusted"
          sub="earned autonomy · roadmap"
          aside={<>{src(d.sources.agents)} <Link href="#/team">Teams</Link></>}
        >
          <div className="scroll-x">
            <table className="table">
              <thead><tr><th>Agent</th><th>Verified</th><th>Unrequested</th><th>Attempts</th><th>Autonomy</th></tr></thead>
              <tbody>
                {d.agents.map((a) => (
                  <tr key={a.name} className={a.autonomy || d.sources.agents === "measured" ? "" : "muted"}>
                    <td><b className="mono nm">{a.name}</b><div className="panel-sub">{a.tool}{a.decisions ? ` · ${a.decisions.toLocaleString("en-US")} decisions` : ""}</div></td>
                    <td>{a.verified != null ? <Meter v={a.verified} /> : "–"}</td>
                    <td>{a.unrequested != null ? <Meter v={a.unrequested} bad={a.unrequested > 12} /> : "–"}</td>
                    <td className="mono">{a.attempts ?? "–"}</td>
                    <td>{a.autonomy ? <span className={`chip ${AUTONOMY[a.autonomy].cls}`}>{AUTONOMY[a.autonomy].text}</span> : <span className="chip">{d.sources.agents === "measured" ? "Not set" : "Not connected"}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="note">Autonomy is earned and reversible: the less an agent's claims verify, the harder the gate on its changes.</p>
        </Panel>

        <Panel title="Governance backlog" sub="policy candidates and expiries" aside={<Link href="#/govern">Open inbox</Link>}>
          {d.backlog.length === 0 ? (
            <p className="panel-sub">No policy candidates waiting for review.</p>
          ) : (
            <ul className="rows">
              {d.backlog.map((b) => (
                <li key={b.id}>
                  <div><b>{b.statement}</b><div className="panel-sub">{b.id} · waiting {b.waiting_days}d</div></div>
                  <div className="chips left"><span className="chip human">{b.sessions} sessions</span><span className="chip">{b.teams} {b.teams === 1 ? "team" : "teams"}</span><span className="chip">{b.developers} devs</span></div>
                </li>
              ))}
            </ul>
          )}
          <p className="panel-sub sect">Expiring soon</p>
          {d.expiring.length === 0 ? (
            <p className="panel-sub">No active policies expiring within 90 days.</p>
          ) : (
            <ul className="rows">
              {d.expiring.map((e) => (
                <li key={e.id}>
                  <div><b>{e.statement}</b><div className="panel-sub">{e.id} · owner {e.owner}</div></div>
                  <span className={`chip ${e.in_days <= 14 ? "warn" : ""}`}>in {e.in_days} days</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </>
  );
}

export default function Exec() {
  const [period, setPeriod] = useState<Period>("30d");
  const q = useExec(period);
  const sessions = q.data?.kpis.sessions;
  return (
    <main className="wrap page exec">
      <PageHead
        crumbs={<>Org <b>›</b> <span>All repositories</span></>}
        title="Can we trust our agent programme?"
        sub="Adherence to our own rules, how often the same correction repeats, and whether claims hold up across every repository. Measured on agents, areas and policies, never on people."
        meta={
          <>
            <Seg<Period> value={period} onChange={setPeriod} options={[{ id: "30d", label: "30 days" }, { id: "90d", label: "90 days" }]} />
            {sessions !== undefined && <span className="chip mono">{sessions.toLocaleString("en-US")} sessions</span>}
            {q.data && (Object.values(q.data.sources).every((s) => s === "measured")
              ? <span className="chip ok">Measured</span>
              : Object.values(q.data.sources).includes("measured")
                ? <span className="chip warn" title="Sections marked Sample data have no measured source yet">Partly measured</span>
                : <span className="chip sim">Illustrative data</span>)}
          </>
        }
      />
      <DataGate q={q}>{(d) => <ExecBody d={d} />}</DataGate>
    </main>
  );
}
