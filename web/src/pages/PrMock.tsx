import { useMemo, useState, type CSSProperties } from "react";
import { Bot, Code2, User } from "lucide-react";
import {
  allDecisions, criteria, criteriaSpans, detail, editsAfterLastTest, flags, lastTestTurn, session, transcript, TYPE_LABEL,
  type CheckName, type ClaimVerdict, type Decision, type DType, type HumanKind, type Origin, type SessionEvent,
} from "../data";
import { Kpi, PageHead, Panel, Seg, TypeChip } from "../ui";
import PrMode from "../pr/PrMode";
import "../styles/pr.css";

const VERDICT = {
  "first-try": { cls: "ok", text: "Met first try" },
  "agent-missed": { cls: "agent", text: "Agent missed it" },
  "requirement-thin": { cls: "warn", text: "Requirement was thin" },
} as const;

const ORIGIN: Record<Origin, { text: string; cls: string }> = {
  requested: { text: "Requested", cls: "ok" },
  agent_initiated_related: { text: "Agent-initiated, related", cls: "" },
  unrequested: { text: "Unrequested", cls: "warn" },
};
const KIND: Record<HumanKind, string> = {
  redirect: "Redirect", reject: "Reject", permission_denied: "Permission denied", revert: "Revert", requirement: "Requirement added", discussion: "Discussion",
};
const CLAIM: Record<ClaimVerdict, string> = { verified: "ok", contradicted: "bad", unsupported: "bad", unverifiable: "warn" };
const CHECK: Record<CheckName, string> = {
  tests_ran: "tests ran", stale_tests: "stale tests", covering_test: "covering test · static estimate", phantom_change: "claimed change is in the diff",
};
const TOOL_TOKENS: Record<string, number> = { read_file: 2400, grep_search: 900, replace: 3100, write_file: 1500, run_shell_command: 1100, write_todos: 600 }; // illustrative

// 0..1 along the session axis
const P = (t: number) => (t - 1) / (session.turns - 1);
const at = (t: number): CSSProperties => ({ ["--p" as string]: P(t).toFixed(4) });

// vertical layout of the timeline, in px
const Y = { aMark: 156, aTop: [10, 54, 98], chipH: 38, strip: 172, stripH: 54, hMark: 262, hTop: [282, 326, 370], bands: 428, bandStep: 28 };

function Timeline({ sel, setSel, filter }: { sel: string; setSel: (id: string) => void; filter: DType | "all" }) {
  const lane = (w: Decision["who"]) => allDecisions.filter((d) => d.who === w);
  const chain = (d: Decision) => sel === d.id || sel === d.overrides;
  return (
    <div className="tl-scroll">
      <div className="tl" style={{ height: Y.bands + criteria.length * Y.bandStep + 8 }}>
        <span className="gl agent" style={{ top: Y.aMark - 8 }}>agent</span>
        <span className="gl" style={{ top: Y.strip + 1 }}>tests</span>
        <span className="gl" style={{ top: Y.strip + 19 }}>edits</span>
        <span className="gl" style={{ top: Y.strip + 37 }}>reads</span>
        <span className="gl human" style={{ top: Y.hMark - 8 }}>human</span>

        {/* the activity strip: what the agent did, by turn */}
        <div className="strip" style={{ top: Y.strip, height: Y.stripH }} />
        <div className="stale at" style={{ ...at(lastTestTurn), top: Y.strip, height: Y.stripH, width: `calc(var(--gw) * ${(1 - P(lastTestTurn)).toFixed(4)})` }} />
        {session.events.map((e: SessionEvent, i) => {
          const row = e.kind === "test" || e.kind === "denied" ? 0 : e.kind === "edit" ? 1 : 2;
          return <i key={i} className={`ev at ev-${e.kind} ${e.ok === false ? "fail" : ""} ${e.revert ? "revert" : ""}`} style={{ ...at(e.t), top: Y.strip + 9 + row * 18 }} title={`T${e.t} · ${e.tool}: ${e.label}`} />;
        })}
        {[1, 10, 20, 30].map((t) => <span key={t} className="axis at" style={{ ...at(t), top: Y.strip + Y.stripH + 3 }}>T{t}</span>)}
        <span className="stale-label" style={{ top: Y.strip + Y.stripH + 3 }} title={`No test run after T${lastTestTurn}. ${editsAfterLastTest} edits since.`}>stale since T{lastTestTurn} · {editsAfterLastTest} edits</span>

        {/* overrule arcs: the human decision points back at the agent proposal it overruled */}
        <svg className="arcs" viewBox={`0 0 1000 ${Y.bands}`} preserveAspectRatio="none" aria-hidden="true">
          {allDecisions.filter((d) => d.overrides).map((d) => {
            const a = allDecisions.find((x) => x.id === d.overrides)!;
            const xa = P(a.turn) * 1000, xh = P(d.turn) * 1000, m = (Y.aMark + Y.hMark) / 2;
            return <path key={d.id} className={chain(d) ? "on" : ""} d={`M${xh} ${Y.hMark} C ${xh} ${m}, ${xa} ${m}, ${xa} ${Y.aMark}`} />;
          })}
        </svg>

        {/* decisions */}
        {allDecisions.map((d) => {
          const list = lane(d.who), level = list.indexOf(d) % 3, agent = d.who === "agent";
          const top = agent ? Y.aTop[level] : Y.hTop[level], mark = agent ? Y.aMark : Y.hMark;
          const stem = agent ? { top: top + Y.chipH, height: mark - top - Y.chipH } : { top: mark, height: top - mark };
          const struck = allDecisions.some((y) => y.overrides === d.id);
          const edge = P(d.turn) > 0.9 ? "r" : P(d.turn) < 0.1 ? "l" : "";
          const dim = filter !== "all" && d.type !== filter;
          return (
            <div key={d.id} className={`dk ${d.who} t-${d.type} ${dim ? "dim" : ""} ${sel === d.id ? "sel" : ""}`}>
              <i className="stem at" style={{ ...at(d.turn), ...stem }} />
              <i className="mk at" style={{ ...at(d.turn), top: mark - 7 }} />
              <button className={`ch at ${edge} ${struck ? "struck" : ""}`} style={{ ...at(d.turn), top }} onClick={() => setSel(d.id)} aria-pressed={sel === d.id}>
                <b>{d.label}</b>
                <span>T{d.turn} · {TYPE_LABEL[d.type]}</span>
              </button>
            </div>
          );
        })}

        {/* acceptance criteria: one band per criterion, one segment per attempt */}
        {criteria.map((c, r) => {
          const spans = criteriaSpans[c.id], top = Y.bands + r * Y.bandStep;
          const last = spans[spans.length - 1], right = P(last.to) < 0.55;
          return (
            <div key={c.id}>
              <span className="gl human" style={{ top: top + 4 }}>{c.id}</span>
              {spans.map((s, k) => (
                <i key={k} className={`band at ${s.outcome}`} style={{ ...at(s.from), top, width: `calc(var(--gw) * ${(P(s.to) - P(s.from)).toFixed(4)})` }} title={`${c.id} attempt ${k + 1}: T${s.from}–T${s.to} · ${s.outcome}`}>{s.outcome === "open" ? "open" : k + 1}</i>
              ))}
              <span className={`bl at ${right ? "" : "left"}`} style={{ ...at(right ? last.to : spans[0].from), top: top + 4 }}>{c.text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Phones: the same story as a vertical thread.
function Thread({ sel, setSel, filter }: { sel: string; setSel: (id: string) => void; filter: DType | "all" }) {
  const items = [
    ...allDecisions.map((d) => ({ t: d.turn, d, e: undefined as SessionEvent | undefined })),
    ...session.events.filter((e) => e.kind === "test" || e.kind === "denied").map((e) => ({ t: e.t, d: undefined as Decision | undefined, e })),
  ].sort((a, b) => a.t - b.t || (a.d ? 1 : 0) - (b.d ? 1 : 0));
  return (
    <ol className="thread">
      {items.map((it, i) => it.d ? (
        <li key={i} className={`th-d ${it.d.who} ${filter !== "all" && it.d.type !== filter ? "dim" : ""}`}>
          <button className={`thc t-${it.d.type} ${sel === it.d.id ? "sel" : ""}`} onClick={() => setSel(it.d!.id)} aria-pressed={sel === it.d.id}>
            <span className="th-top"><i />{it.d.who === "agent" ? <Bot size={12} /> : <User size={12} />}<b>{it.d.label}</b></span>
            <span className="th-meta">T{it.d.turn} · {TYPE_LABEL[it.d.type]}{it.d.overrides ? ` · overrules ${allDecisions.find((x) => x.id === it.d!.overrides)!.label}` : ""}</span>
          </button>
        </li>
      ) : (
        <li key={i} className={`th-e ${it.e!.ok === false ? "fail" : it.e!.kind === "denied" ? "denied" : "ok"}`}>
          <span className="mono">T{it.t}</span> {it.e!.label}
        </li>
      ))}
    </ol>
  );
}

function Detail({ d, setSel }: { d: Decision; setSel: (id: string) => void }) {
  const x = detail[d.id] ?? {};
  const overruled = allDecisions.find((y) => y.overrides === d.id);
  const overrides = d.overrides ? allDecisions.find((y) => y.id === d.overrides) : undefined;
  const quoteTurns = (ts?: number[]) => (ts ?? []).filter((t) => transcript[t]).map((t) => ({ t, ...transcript[t] }));
  const asked = quoteTurns(x.asked), against = quoteTurns(x.against);
  const agent = d.who === "agent";
  return (
    <>
      <div className="dt-chips">
        <span className={`chip ${d.who}`}>{agent ? <Bot size={12} /> : <User size={12} />}{d.who}</span>
        <TypeChip t={d.type} />
        <span className="chip mono">T{d.turn} · {d.time}</span>
        {x.origin && <span className={`chip ${ORIGIN[x.origin].cls}`}>{ORIGIN[x.origin].text}</span>}
        {d.kind && <span className="chip human">{KIND[d.kind]}</span>}
      </div>
      <h3 className="dt-title">{d.label}</h3>
      <p className="dt-sum">{d.summary}</p>

      {overrides && <div className="callout human">Overrules <button className="inline" onClick={() => setSel(overrides.id)}>{overrides.label}</button> (T{overrides.turn}). The agent proposed it, the human chose differently.</div>}
      {overruled && <div className="callout human">Overruled at T{overruled.turn} by <button className="inline" onClick={() => setSel(overruled.id)}>{overruled.label}</button>.</div>}

      <div className="dl">Evidence</div>
      {asked.map((q) => <blockquote key={q.t} className="user"><span>Your words · T{q.t}</span>“{q.text}”</blockquote>)}
      {against.map((q) => <blockquote key={q.t} className="user against"><span>Contradicts your words · T{q.t}</span>“{q.text}”</blockquote>)}
      {agent && x.origin && x.origin !== "requested" && !asked.length && !against.length && <div className="callout warn">No user turn asks for this. Code checked: no user turn mentions it.</div>}
      {agent && <blockquote className="agent"><span>Agent said · T{d.turn}</span>“{d.quote.text}”</blockquote>}
      {d.rationale && <p className="dt-note"><b>Agent's stated rationale (unverified):</b> {d.rationale}</p>}

      {x.alternatives && (
        <>
          <div className="dl">Alternatives considered</div>
          <ul className="alts">{x.alternatives.map((a) => <li key={a.text} className={a.chosen ? "chosen" : ""}>{a.text}{a.chosen && <span className="chip">chosen</span>}</li>)}</ul>
        </>
      )}

      <div className="dl">Thread</div>
      <ol className="chain">
        {x.trigger && <li><span>Before</span>{x.trigger}</li>}
        <li className="here"><span>This</span>{d.label}</li>
        {x.after && <li><span>After</span>{x.after}</li>}
      </ol>

      {x.diff && (
        <>
          <div className="dl"><Code2 size={12} /> {x.diff.file}</div>
          <pre className="diff mono">{x.diff.lines.map((l, i) => <span key={i} className={l[0] === "+" ? "add" : l[0] === "-" ? "del" : ""}>{l}</span>)}</pre>
        </>
      )}
      {!x.diff && d.code && <div className="code mono"><Code2 size={12} /> {d.code}</div>}

      {x.claims && (
        <>
          <div className="dl">Claims checked by code</div>
          <ul className="claims">
            {x.claims.map((c) => (
              <li key={c.text}>
                <span className={`chip ${CLAIM[c.verdict]}`}>{c.verdict}</span>
                <b>“{c.text}”</b>
                <small className="mono">{CHECK[c.check]}</small>
                <p>{c.evidence}</p>
              </li>
            ))}
          </ul>
        </>
      )}

      {(x.struggle || x.blast) && (
        <div className="stats">
          {x.struggle && <div><b className="mono">{x.struggle.edits}</b> edits <b className="mono">{x.struggle.reverts}</b> reverts <b className="mono">{x.struggle.failed_runs}</b> failed runs</div>}
          {x.blast && <div><b className="mono">{x.blast.callers}</b> callers · covering test: {x.blast.covered ? "yes" : "none"} <small>(static estimate)</small></div>}
        </div>
      )}

      {d.rule && <div className={`callout ${d.rule.status === "followed" ? "ok" : "bad"}`}>Skill rule <b>{d.rule.status}</b>: {d.rule.text}</div>}
    </>
  );
}

export default function PrMock() {
  const [sel, setSel] = useState("d2");
  const [filter, setFilter] = useState<DType | "all">("all");
  const [metric, setMetric] = useState<"calls" | "tokens">("calls");

  const d = allDecisions.find((x) => x.id === sel)!;
  const rules = useMemo(() => allDecisions.filter((x) => x.rule), []);
  const followed = rules.filter((x) => x.rule!.status === "followed").length;
  const agentN = allDecisions.filter((x) => x.who === "agent").length;
  const overrules = allDecisions.filter((x) => x.overrides).length;
  const unsupported = Object.values(detail).flatMap((x) => x.claims ?? []).filter((c) => c.verdict === "unsupported" || c.verdict === "contradicted").length;
  const attempts = criteria.reduce((n, c) => n + criteriaSpans[c.id].length, 0) / criteria.length;
  const firstTry = criteria.filter((c) => criteriaSpans[c.id].length === 1).length;
  const present = Array.from(new Set(allDecisions.map((x) => x.type)));

  const sessionTools = useMemo(() => {
    const m = new Map<string, { name: string; calls: number; tokens: number }>();
    session.events.forEach((e) => {
      const r = m.get(e.tool) ?? { name: e.tool, calls: 0, tokens: 0 };
      r.calls += 1; r.tokens += TOOL_TOKENS[e.tool] ?? 1000; m.set(e.tool, r);
    });
    return [...m.values()].sort((a, b) => b.calls - a.calls);
  }, []);
  const max = Math.max(...sessionTools.map((t) => t[metric]));

  return (
    <main className="wrap page">
      <PageHead
        crumbs={<>Company <b>›</b> Payments <b>›</b> <span>PR #482</span></>}
        title="Add retry to the payments client"
        meta={<>
          <span className="chip agent"><Bot size={12} /> Gemini CLI</span>
          <span className="chip">{session.turns} turns · 1h 12m</span>
          <span className="chip">feat/retries</span>
          <span className="chip sim">Illustrative data</span>
          <PrMode mode="mock" />
        </>}
      />

      <section className="kpis kpis-pr" aria-label="Summary">
        <Kpi value={allDecisions.length} label="decisions" sub={<><i className="dotk agent" />{agentN} agent <i className="dotk human" />{allDecisions.length - agentN} human</>} />
        <Kpi value={overrules} tone="hot" label="human overrules" sub="redirect, reject, permission denied" />
        <Kpi value={attempts.toFixed(2)} label="attempts per criterion" sub={`${firstTry} of ${criteria.length} met first try`} />
        <Kpi value={unsupported} tone="bad" label="unsupported claims" sub="checked by code" />
        <Kpi value={`${followed}/${rules.length}`} label="skill rules followed" sub={`${Math.round((followed / rules.length) * 100)}% adherence`} />
      </section>

      <Panel title="What the PR comment flags" sub={`${flags.length} flags · each links to its decision`}>
        <ul className="flags">
          {flags.map((f) => (
            <li key={f.text}>
              <span className={`chip ${f.tone}`}>{f.tone === "bad" ? "evidence" : "review"}</span>
              <div><b>{f.text}</b><small>{f.note}</small></div>
              <button className="pr-link mono" onClick={() => { setSel(f.decision); scrollTo({ top: 0, behavior: "smooth" }); }}>{f.decision === "d9" ? "T47" : `T${allDecisions.find((x) => x.id === f.decision)!.turn}`}</button>
            </li>
          ))}
        </ul>
      </Panel>

      <section className="pr-main">
        <Panel
          title="Session timeline"
          sub="turns T1–T48 · agent decisions above, human decisions below"
          aside={
            <div className="filters">
              <button className={`chip ${filter === "all" ? "on" : ""}`} onClick={() => setFilter("all")}>All</button>
              {present.map((t) => (
                <button key={t} className={`chip t-${t} ${filter === t ? "on" : ""}`} onClick={() => setFilter(filter === t ? "all" : t)}><i />{TYPE_LABEL[t]}</button>
              ))}
            </div>
          }
        >
          <div className="tl-wrap"><Timeline sel={sel} setSel={setSel} filter={filter} /></div>
          <div className="th-wrap"><Thread sel={sel} setSel={setSel} filter={filter} /></div>
          <ul className="legend">
            <li><i className="lg mk-a" /> agent decision</li>
            <li><i className="lg mk-h" /> human decision</li>
            <li><i className="lg arc" /> overrule</li>
            <li><i className="lg e-edit" /> edit</li>
            <li><i className="lg e-rev" /> edit later reverted</li>
            <li><i className="lg e-ok" /> test run passed</li>
            <li><i className="lg e-bad" /> test run failed</li>
            <li><i className="lg e-den" /> permission denied</li>
            <li><i className="lg b-acc" /> attempt accepted</li>
            <li><i className="lg b-rej" /> attempt rejected</li>
          </ul>
        </Panel>

        <aside className="panel detail" aria-label="Decision detail"><Detail d={d} setSel={setSel} /></aside>
      </section>

      <Panel title="Acceptance criteria" sub="from the prompt and the ticket · attempts match the timeline bands">
        <div className="ladders">
          {criteria.map((c) => {
            const v = VERDICT[c.verdict];
            const ds = allDecisions.filter((x) => x.criterion === c.id);
            return (
              <div key={c.id} className="ladder">
                <div className="ladder-t"><span className="mono id">{c.id}</span><b>{c.text}</b><span className="src">{c.source}</span></div>
                <div className="rungs">
                  {ds.map((x) => (
                    <button key={x.id} className={`rung ${x.who}`} style={{ ["--c" as string]: `var(--t-${x.type})` }} onClick={() => { setSel(x.id); scrollTo({ top: 0, behavior: "smooth" }); }} title={`${x.label} · T${x.turn}`}><i /></button>
                  ))}
                  <span className="mono att">{criteriaSpans[c.id].length} attempt{criteriaSpans[c.id].length > 1 ? "s" : ""}</span>
                </div>
                <div className="ladder-v"><span className={`chip ${v.cls}`}>{v.text}</span><p>{c.note}</p></div>
              </div>
            );
          })}
        </div>
        <p className="sim-note">Cause proposed by the model from the turns above. A reviewer confirms it before it counts.</p>
      </Panel>

      <section className="grid-2">
        <Panel title="Tool use" sub="from the session · tokens are illustrative" aside={<Seg value={metric} onChange={setMetric} options={[{ id: "calls", label: "Calls" }, { id: "tokens", label: "Tokens" }]} />}>
          {sessionTools.map((t) => (
            <div className="tbar" key={t.name}>
              <span className="mono">{t.name}</span>
              <span className="pr-track"><i style={{ width: `${(t[metric] / max) * 100}%` }} /></span>
              <b className="mono">{metric === "tokens" ? `${(t.tokens / 1000).toFixed(1)}k` : t.calls}</b>
            </div>
          ))}
        </Panel>
        <Panel title="Skill adherence" sub={`${followed} of ${rules.length} rules followed`}>
          <ul className="rules">
            {rules.map((x) => (
              <li key={x.id}>
                <span className={`chip ${x.rule!.status === "followed" ? "ok" : "bad"}`}>{x.rule!.status}</span>
                <span>{x.rule!.text}</span>
                <button className="pr-link mono" onClick={() => { setSel(x.id); scrollTo({ top: 0, behavior: "smooth" }); }}>T{x.turn}</button>
              </li>
            ))}
          </ul>
        </Panel>
      </section>
    </main>
  );
}
