import { useEffect, useRef, useState } from "react";
import { ArrowRight, Layers, TrendingDown, TrendingUp } from "lucide-react";
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

function Delta({ d, goodWhenUp = true, unit = "pts" }: { d: number | null; goodWhenUp?: boolean; unit?: string }) {
  if (d === null) return <span className="delta">no earlier period</span>;
  const good = d > 0 === goodWhenUp;
  const Icon = d > 0 ? TrendingUp : TrendingDown;
  return <span className={`delta ${good ? "up" : "down"}`}><Icon size={12} /> {d > 0 ? "+" : "−"}{Math.abs(d)} {unit}</span>;
}

function Trend({ d }: { d: ExecData }) {
  const [ref, w] = useWidth();
  const H = 244, L = 34, R = 44, T = 32, B = 26;
  const a = d.adherence, o = d.repeat_overrides, labels = d.weeks.map(shortDay);
  const n = a.length;
  const x = (i: number) => L + (i * (w - L - R)) / Math.max(1, n - 1);
  const ya = (v: number) => T + ((100 - v) / 40) * (H - T - B);
  const yo = (v: number) => T + ((14 - v) / 14) * (H - T - B);
  // a week with no value (null) leaves a gap in the line instead of a zero
  const path = (vs: (number | null)[], y: (v: number) => number) => {
    let pen = false;
    return vs.map((v, i) => { if (v === null) { pen = false; return ""; } const s = `${pen ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`; pen = true; return s; }).filter(Boolean).join(" ");
  };
  const lastOf = (vs: (number | null)[]) => { for (let i = vs.length - 1; i >= 0; i--) if (vs[i] !== null) return i; return -1; };
  const la = lastOf(a), lo = lastOf(o);
  const step = w < 520 ? 3 : 1;
  return (
    <div ref={ref} className="chart">
      <svg width={w} height={H} role="img" aria-label="Skill adherence and repeat-override rate by week, with policy publish dates">
        {[60, 70, 80, 90, 100].map((v) => (
          <g key={v}>
            <line x1={L} x2={w - R} y1={ya(v)} y2={ya(v)} className="grid" />
            <text x={L - 8} y={ya(v) + 4} textAnchor="end" className="ax">{v}%</text>
          </g>
        ))}
        {[0, 7, 14].map((v) => <text key={v} x={w - R + 8} y={yo(v) + 4} className="ax human">{v}</text>)}
        {d.policy_events.map((e) => (
          <g key={e.id}>
            <line x1={x(e.week)} x2={x(e.week)} y1={T - 6} y2={H - B} className="event" />
            <text x={x(e.week)} y={T - 12} textAnchor={x(e.week) < 70 ? "start" : x(e.week) > w - 90 ? "end" : "middle"} className="ev-t">{e.id}{w >= 520 ? " published" : ""}</text>
          </g>
        ))}
        <path d={path(a, ya)} className="line agent" />
        <path d={path(o, yo)} className="line human" />
        {a.map((v, i) => v !== null && <circle key={i} cx={x(i)} cy={ya(v)} r={i === la ? 4.5 : 2.5} className="pt agent"><title>{labels[i]}: {v}% adherence</title></circle>)}
        {o.map((v, i) => v !== null && <circle key={i} cx={x(i)} cy={yo(v)} r={i === lo ? 4.5 : 2.5} className="pt human"><title>{labels[i]}: {v} repeat overrides per 100 sessions</title></circle>)}
        {la >= 0 && <text x={Math.min(x(la) + 10, w - 36)} y={ya(a[la]!) - 8} className="end agent">{a[la]}%</text>}
        {lo >= 0 && <text x={Math.min(x(lo) + 10, w - 36)} y={yo(o[lo]!) + 16} className="end human">{o[lo]}</text>}
        {n === 0 && <text x={w / 2} y={H / 2} textAnchor="middle" className="ax">No weeks to show</text>}
        {labels.map((l, i) => (i % step === 0 || i === n - 1) && (
          <text key={i} x={x(i)} y={H - 6} textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"} className="ax">{l}</text>
        ))}
      </svg>
      <p className="legend-row">
        <span><i className="sw agent" />Skill adherence, % of agent decisions</span>
        <span><i className="sw human" />Repeat overrides per 100 sessions</span>
        <span className="mono dim">{d.period === "30d" ? "last 5 weeks" : "last 12 weeks"}</span>
      </p>
    </div>
  );
}

function Mix({ d }: { d: ExecData }) {
  const [ref, w] = useWidth();
  const H = w > 560 ? 290 : 200, L = 30, T = 8, B = 22;
  const weeks = d.weeks.length;
  const totals = Array.from({ length: weeks }, (_, i) => TYPE_ORDER.reduce((s, t) => s + d.mix[t][i], 0));
  const max = Math.max(40, Math.ceil(Math.max(...totals, 0) / 40) * 40);
  const slot = (w - L) / weeks, bw = Math.min(28, slot * 0.64);
  const y = (v: number) => T + (1 - v / max) * (H - T - B);
  return (
    <div ref={ref} className="chart">
      <svg width={w} height={H} role="img" aria-label="Decisions per week by type">
        {[0, 40, 80, 120].filter((v) => v <= max).map((v) => (
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
                const r = <rect key={t} x={cx} y={y(acc + v)} width={bw} height={y(acc) - y(acc + v) - 1} rx="2" style={{ fill: `var(--t-${t})` }}><title>{shortDay(d.weeks[i])} · {TYPE_LABEL[t]}: {v}</title></rect>;
                acc += v;
                return r;
              })}
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
        <Kpi tone="ok" value={n(k.adherence.v, (x) => `${x}%`)} label="Skill adherence" sub={<><Delta d={k.adherence.d} /> vs prior</>} />
        <Kpi tone="hot" value={n(k.override.v, (x) => x.toFixed(1))} label="Repeat overrides per 100 sessions"
          sub={d.sources.kpis === "measured" ? <>{k.override.before === null ? "no earlier period" : `was ${k.override.before} in the period before`}</> : <>was {k.override.before} before {headline?.id ?? "the policy"}</>} />
        <Kpi value={n(k.verified.v, (x) => `${x}%`)} label="Claims verified by code" sub={<><Delta d={k.verified.d} /> vs prior</>} />
        <Kpi value={n(k.unrequested.v, (x) => `${x}%`)} label="Changes nobody asked for" sub={<><Delta d={k.unrequested.d} goodWhenUp={false} /> vs prior</>} />
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
              <i className="agent" style={{ width: `${100 - humanShare}%` }}><span className="w">Agent&nbsp;</span>{100 - humanShare}%</i>
              <i className="human" style={{ width: `${humanShare}%` }}><span className="w">Human&nbsp;</span>{humanShare}%</i>
            </div>
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
          <ul className="kinds">
            {d.human_kinds.map((h) => (
              <li key={h.kind}><span>{h.label}</span><span className="track"><i style={{ width: `${h.pct * 2.2}%` }} /></span><b className="mono">{h.pct}%</b></li>
            ))}
          </ul>
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
          <ul className="rows">
            {d.backlog.map((b) => (
              <li key={b.id}>
                <div><b>{b.statement}</b><div className="panel-sub">{b.id} · waiting {b.waiting_days}d</div></div>
                <div className="chips left"><span className="chip human">{b.sessions} sessions</span><span className="chip">{b.teams} {b.teams === 1 ? "team" : "teams"}</span><span className="chip">{b.developers} devs</span></div>
              </li>
            ))}
          </ul>
          <p className="panel-sub sect">Expiring soon</p>
          <ul className="rows">
            {d.expiring.map((e) => (
              <li key={e.id}>
                <div><b>{e.statement}</b><div className="panel-sub">{e.id} · owner {e.owner}</div></div>
                <span className={`chip ${e.in_days <= 14 ? "warn" : ""}`}>in {e.in_days} days</span>
              </li>
            ))}
          </ul>
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
        crumbs={<>Company <b>›</b> <span>Agent programme</span></>}
        title="Can we trust our agent programme?"
        sub="Adherence to our own rules, how often the same correction repeats, and whether claims hold up. Measured on agents, areas and policies, never on people."
        meta={
          <>
            <Seg<Period> value={period} onChange={setPeriod} options={[{ id: "30d", label: "30 days" }, { id: "90d", label: "90 days" }]} />
            <span className="chip"><Layers size={12} /> All teams</span>
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
