import { useEffect, useRef, useState } from "react";
import { ArrowRight, Layers, TrendingDown, TrendingUp } from "lucide-react";
import { TYPE_LABEL } from "../data";
import {
  adherence, agents, backlog, expiring, humanKinds, humanPerWeek, kpis, mix, policyEvents,
  repeatOverrides, rework, typeOrder, weekLabels, type Autonomy, type Period,
} from "../data.exec";
import { Kpi, PageHead, Panel, Seg, TypeChip } from "../ui";
import "../styles/exec.css";

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

function Delta({ d, goodWhenUp = true, unit = "pts" }: { d: number; goodWhenUp?: boolean; unit?: string }) {
  const good = d > 0 === goodWhenUp;
  const Icon = d > 0 ? TrendingUp : TrendingDown;
  return <span className={`delta ${good ? "up" : "down"}`}><Icon size={12} /> {d > 0 ? "+" : "−"}{Math.abs(d)} {unit}</span>;
}

function Trend({ from, period }: { from: number; period: Period }) {
  const [ref, w] = useWidth();
  const H = 244, L = 34, R = 44, T = 32, B = 26;
  const a = adherence.slice(from), o = repeatOverrides.slice(from), labels = weekLabels.slice(from);
  const n = a.length;
  const x = (i: number) => L + (i * (w - L - R)) / (n - 1);
  const ya = (v: number) => T + ((100 - v) / 40) * (H - T - B);
  const yo = (v: number) => T + ((14 - v) / 14) * (H - T - B);
  const path = (vs: number[], y: (v: number) => number) => vs.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
  const events = policyEvents.filter((e) => e.week >= from).map((e) => ({ ...e, i: e.week - from }));
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
        {events.map((e) => (
          <g key={e.id}>
            <line x1={x(e.i)} x2={x(e.i)} y1={T - 6} y2={H - B} className="event" />
            <text x={x(e.i)} y={T - 12} textAnchor={x(e.i) < 70 ? "start" : x(e.i) > w - 90 ? "end" : "middle"} className="ev-t">{e.id}{w >= 520 ? " published" : ""}</text>
          </g>
        ))}
        <path d={path(a, ya)} className="line agent" />
        <path d={path(o, yo)} className="line human" />
        {a.map((v, i) => <circle key={i} cx={x(i)} cy={ya(v)} r={i === n - 1 ? 4.5 : 2.5} className="pt agent"><title>{labels[i]}: {v}% adherence</title></circle>)}
        {o.map((v, i) => <circle key={i} cx={x(i)} cy={yo(v)} r={i === n - 1 ? 4.5 : 2.5} className="pt human"><title>{labels[i]}: {v} repeat overrides per 100 sessions</title></circle>)}
        <text x={x(n - 1) + 10} y={ya(a[n - 1]) - 8} className="end agent">{a[n - 1]}%</text>
        <text x={x(n - 1) + 10} y={yo(o[n - 1]) + 16} className="end human">{o[n - 1]}</text>
        {labels.map((l, i) => (i % step === 0 || i === n - 1) && (
          <text key={i} x={x(i)} y={H - 6} textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"} className="ax">{l}</text>
        ))}
      </svg>
      <p className="legend-row">
        <span><i className="sw agent" />Skill adherence, % of agent decisions</span>
        <span><i className="sw human" />Repeat overrides per 100 sessions</span>
        <span className="mono dim">{period === "30d" ? "last 5 weeks" : "last 12 weeks"}</span>
      </p>
    </div>
  );
}

function Mix({ from }: { from: number }) {
  const [ref, w] = useWidth();
  const H = w > 560 ? 290 : 200, L = 30, T = 8, B = 22;
  const weeks = mix.architecture.length - from;
  const totals = Array.from({ length: weeks }, (_, i) => typeOrder.reduce((s, t) => s + mix[t][from + i], 0));
  const max = Math.ceil(Math.max(...totals) / 40) * 40;
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
              {typeOrder.map((t) => {
                const v = mix[t][from + i];
                const r = <rect key={t} x={cx} y={y(acc + v)} width={bw} height={y(acc) - y(acc + v) - 1} rx="2" style={{ fill: `var(--t-${t})` }}><title>{weekLabels[from + i]} · {TYPE_LABEL[t]}: {v}</title></rect>;
                acc += v;
                return r;
              })}
              {(weeks < 8 || i % 2 === 0) && <text x={cx + bw / 2} y={H - 6} textAnchor="middle" className="ax">{weekLabels[from + i]}</text>}
            </g>
          );
        })}
      </svg>
      <div className="chips">{typeOrder.map((t) => <TypeChip key={t} t={t} />)}</div>
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

export default function Exec() {
  const [period, setPeriod] = useState<Period>("30d");
  const k = kpis[period];
  const from = period === "30d" ? 7 : 0;

  const humanShare = Math.round(
    (humanPerWeek.slice(from).reduce((s, v) => s + v, 0) /
      typeOrder.reduce((s, t) => s + mix[t].slice(from).reduce((a, v) => a + v, 0), 0)) * 100,
  );

  const r = rework[period];
  const total = r.first + r.missed + r.thin;
  const pct = (v: number) => Math.round((v / total) * 100);
  const thinOfRework = Math.round((r.thin / (r.missed + r.thin)) * 100);
  const p12 = policyEvents.find((e) => e.id === "P-12")!;

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
            <span className="chip mono">{k.sessions.toLocaleString("en-US")} sessions</span>
            <span className="chip sim">Illustrative data</span>
          </>
        }
      />

      <section className="kpis five" aria-label="Summary">
        <Kpi tone="ok" value={`${k.adherence.v}%`} label="Skill adherence" sub={<><Delta d={k.adherence.d} /> vs prior</>} />
        <Kpi tone="hot" value={k.override.v.toFixed(1)} label="Repeat overrides per 100 sessions" sub={<>was {k.override.before} before P-12</>} />
        <Kpi value={`${k.verified.v}%`} label="Claims verified by code" sub={<><Delta d={k.verified.d} /> vs prior</>} />
        <Kpi value={`${k.unrequested.v}%`} label="Changes nobody asked for" sub={<><Delta d={k.unrequested.d} goodWhenUp={false} /> vs prior</>} />
        <Kpi value={k.pending.v} label="Policies waiting for approval" sub={<>oldest {k.pending.oldestDays} days</>} />
      </section>

      <Panel
        title="Is governance working?"
        sub={`Repeat overrides ${repeatOverrides[p12.week - 1]} → ${repeatOverrides[11]} per 100 sessions since ${p12.id} was published. Associated with the policy, not proven caused by it.`}
        aside={<Link href="#/govern">Policies</Link>}
      >
        <Trend from={from} period={period} />
      </Panel>

      <div className="grid-7-5">
        <Panel title="What agents and people decide" sub="decisions per week, by type" aside={<Link href="#/pr">Example PR</Link>}>
          <Mix from={from} />
          <div className="share">
            <div className="share-bar" role="img" aria-label={`Agent decided ${100 - humanShare}%, human decided ${humanShare}%`}>
              <i className="agent" style={{ width: `${100 - humanShare}%` }}><span className="w">Agent&nbsp;</span>{100 - humanShare}%</i>
              <i className="human" style={{ width: `${humanShare}%` }}><span className="w">Human&nbsp;</span>{humanShare}%</i>
            </div>
          </div>
        </Panel>

        <div className="stackcol">
        <Panel title="Why criteria needed rework" sub={`${total} acceptance criteria`} aside={<Link href="#/team">Teams</Link>}>
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
        <Panel title="Where human decisions come from" sub="share of human decisions, by how they entered the record">
          <ul className="kinds">
            {humanKinds.map((h) => (
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
          aside={<Link href="#/team">Teams</Link>}
        >
          <div className="scroll-x">
            <table className="table">
              <thead><tr><th>Agent</th><th>Verified</th><th>Unrequested</th><th>Attempts</th><th>Autonomy</th></tr></thead>
              <tbody>
                {agents.map((a) => (
                  <tr key={a.name} className={a.autonomy ? "" : "muted"}>
                    <td><b className="mono nm">{a.name}</b><div className="panel-sub">{a.tool}{a.decisions ? ` · ${a.decisions.toLocaleString("en-US")} decisions` : ""}</div></td>
                    <td>{a.verified != null ? <Meter v={a.verified} /> : "–"}</td>
                    <td>{a.unrequested != null ? <Meter v={a.unrequested} bad={a.unrequested > 12} /> : "–"}</td>
                    <td className="mono">{a.attempts ?? "–"}</td>
                    <td>{a.autonomy ? <span className={`chip ${AUTONOMY[a.autonomy].cls}`}>{AUTONOMY[a.autonomy].text}</span> : <span className="chip">Not connected</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="note">Autonomy is earned and reversible: the less an agent's claims verify, the harder the gate on its changes.</p>
        </Panel>

        <Panel title="Governance backlog" sub="policy candidates and expiries" aside={<Link href="#/govern">Open inbox</Link>}>
          <ul className="rows">
            {backlog.map((b) => (
              <li key={b.id}>
                <div><b>{b.statement}</b><div className="panel-sub">{b.id} · waiting {b.waitingDays}d</div></div>
                <div className="chips left"><span className="chip human">{b.sessions} sessions</span><span className="chip">{b.teams} {b.teams === 1 ? "team" : "teams"}</span><span className="chip">{b.developers} devs</span></div>
              </li>
            ))}
          </ul>
          <p className="panel-sub sect">Expiring soon</p>
          <ul className="rows">
            {expiring.map((e) => (
              <li key={e.id}>
                <div><b>{e.statement}</b><div className="panel-sub">{e.id} · owner {e.owner}</div></div>
                <span className={`chip ${e.inDays <= 14 ? "warn" : ""}`}>in {e.inDays} days</span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </main>
  );
}
