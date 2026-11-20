// The lower sections of an analysis page: governance, review findings, the session timeline and the decision story.
// One pattern for all of them: a bold statement, one muted meta line, italic quotes, and nothing decorative.
import { Bot, User } from "lucide-react";
import type { Driver, Governance, GNode, GovDecision, Outcome, TimelineItem } from "../api";
import { Panel, Seg } from "../ui";

const short = (id: string) => id.split("::").slice(1).join("::") || id;
const base = (p: string) => p.split("/").pop() ?? p;
const tnum = (t: string) => Number(t.replace(/\D/g, "")) || 0;
const plural = (c: number, word: string) => `${c} ${word}${c === 1 ? "" : "s"}`;

export const KIND_LABEL: Record<string, string> = {
  choice: "Agent choice", redirect: "Redirected", reject: "Rejected", requirement: "Added requirement",
  discussion: "Chose in discussion", permission_denied: "Denied tool call",
};
const FLAG_LABEL: Record<string, string> = {
  "new-dependency": "New dependency", "skipped-test": "Skipped test", unsupported: "Unsupported claim", "async-gap": "Async gap",
};
const OUTCOME_LABEL: Record<Outcome, string> = {
  ok: "", overruled: "Overruled", reverted: "Reverted", rule_violated: "Rule not followed", unverified: "Claim not backed",
};
export const DRIVER: Record<Driver, string> = { user_asked: "You asked", agent_decided: "Agent decided", not_stated: "No reason in session" };

// a turn id, clickable: opens the quote in the detail panel
function Turn({ id, onClick }: { id: string; onClick: () => void }) {
  return <button className="rv-turn" onClick={onClick}>{id}</button>;
}

// the functions a decision touched, as plain links
function On({ ids, nodes, onNode }: { ids: string[]; nodes: Record<string, GNode>; onNode: (id: string) => void }) {
  const known = ids.filter((n) => nodes[n]);
  if (!known.length) return null;
  return (
    <p className="rv-meta">
      On {known.map((n, i) => <span key={n}>{i > 0 && ", "}<button className="rv-fn" onClick={() => onNode(n)}>{short(n)}</button></span>)}
    </p>
  );
}

export function GovernancePanel({ g, nodes, sel, onTurn, onNode }: {
  g: Governance; nodes: Record<string, GNode>; sel: string | null; onTurn: (t: string) => void; onNode: (id: string) => void;
}) {
  if (!g.available) {
    return (
      <Panel title="Governance">
        <p className="rv-empty">No governance data for this push. It needs an agent session.</p>
      </Panel>
    );
  }
  const human = g.decisions.filter((d) => d.actor === "human");
  const agent = g.decisions.filter((d) => d.actor === "agent");
  const tools = Object.entries(g.tool_stats).sort((x, y) => y[1].calls - x[1].calls);
  const steering = g.steering_files.length ? g.steering_files.join(", ") : "no steering files";

  const decision = (d: GovDecision) => (
    <li key={d.turn + d.kind + d.quote.slice(0, 12)} className={sel && d.nodes?.includes(sel) ? "rv-item hot" : "rv-item"}>
      <p className="rv-main">
        <span className="rv-kind">{KIND_LABEL[d.kind] ?? d.kind}</span>
        {" "}<b>{d.choice || d.proposal}</b>
        {d.outcome && d.outcome !== "ok" && <span className="rv-tag bad">{OUTCOME_LABEL[d.outcome]}</span>}
      </p>
      {d.proposal && d.choice && <p className="rv-meta">Agent proposed: {d.proposal}</p>}
      {d.quote && <p className="rv-quote"><Turn id={d.turn} onClick={() => onTurn(d.turn)} /> <i>“{d.quote}”</i></p>}
      <On ids={d.nodes ?? []} nodes={nodes} onNode={onNode} />
      {d.rule && (
        <p className="rv-meta">Rule: {d.rule}
          {d.rule_followed === true && <span className="rv-tag ok">followed</span>}
          {d.rule_followed === false && <span className="rv-tag bad">not followed</span>}
        </p>
      )}
    </li>
  );

  return (
    <Panel title="Governance" sub={`${g.human_interventions} human intervention${g.human_interventions === 1 ? "" : "s"} · ${g.attempts} attempt${g.attempts === 1 ? "" : "s"} · ${g.steering_rules} steering rules from ${steering}`}>
      {g.flags.length > 0 && (
        <div className="rv-flags">
          {g.flags.map((f) => {
            const target = f.nodes?.find((n) => nodes[n]);
            const label = `${FLAG_LABEL[f.flag] ?? f.flag}${f.path ? ` · ${base(f.path)}` : ""}`;
            return target
              ? <button key={f.flag + f.path} className="rv-tag bad" title={`${f.detail} · show ${short(target)} in the graph`} onClick={() => onNode(target)}>{label}</button>
              : <span key={f.flag + f.path} className="rv-tag bad" title={f.detail}>{label}</span>;
          })}
        </div>
      )}

      {g.highlights.length > 0 && (
        <ul className="rv-list">
          {g.highlights.map((h) => (
            <li key={h.turn + h.text} className="rv-item">
              <p className="rv-main">
                <span className={`rv-kind ${h.kind === "went_right" ? "ok" : "bad"}`}>{h.kind === "went_right" ? "Went right" : "Went wrong"}</span>
                {" "}<b>{h.text}</b>
              </p>
              {h.quote && <p className="rv-quote"><Turn id={h.turn} onClick={() => onTurn(h.turn)} /> <i>“{h.quote}”</i></p>}
              <On ids={h.nodes ?? []} nodes={nodes} onNode={onNode} />
            </li>
          ))}
        </ul>
      )}

      {g.decisions.length === 0 && <p className="rv-empty">No decisions were found in this session.</p>}
      {human.length > 0 && (
        <>
          <h4 className="rv-h">A person stepped in</h4>
          <ul className="rv-list">{human.map(decision)}</ul>
        </>
      )}
      {agent.length > 0 && (
        <>
          <h4 className="rv-h">The agent decided</h4>
          <ul className="rv-list">{agent.map(decision)}</ul>
        </>
      )}
      {tools.length > 0 && (
        <p className="rv-foot">Tools: {tools.map(([n, t]) => `${n} ×${t.calls}${t.tokens ? ` (${t.tokens.toLocaleString()} tokens)` : ""}`).join(" · ")}</p>
      )}
    </Panel>
  );
}

export function ReviewFindings({ findings, onTurn, onFunction }: {
  findings: { id: string | number; kind: string; finding: string; functions: string[]; evidence: { turn: string; quote: string }[] }[];
  onTurn: (t: string) => void; onFunction: (id: string) => void;
}) {
  return (
    <Panel title="Review findings" sub={findings.length ? `${findings.length} ${findings.length === 1 ? "finding" : "findings"}` : undefined}>
      {findings.length === 0 ? <p className="rv-empty">No review findings.</p> : (
        <ul className="rv-list">
          {findings.map((f) => (
            <li key={f.id} className="rv-item">
              <p className="rv-main"><span className="rv-kind bad">{f.kind.replace(/_/g, " ")}</span> <b>{f.finding}</b></p>
              {f.evidence.map((e) => <p key={e.turn + e.quote} className="rv-quote"><Turn id={e.turn} onClick={() => onTurn(e.turn)} /> <i>“{e.quote}”</i></p>)}
              {f.functions[0] && <p className="rv-meta">On <button className="rv-fn" onClick={() => onFunction(f.functions[0])}>{short(f.functions[0])}</button></p>}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

// ---- Session timeline: the graph of turns. Each point is one turn; its colour is what happened there.

const LEGEND: { cls: string; label: string }[] = [
  { cls: "human", label: "You asked" },
  { cls: "agent", label: "Agent edit" },
  { cls: "ok", label: "Tests passed" },
  { cls: "bad", label: "Tests failed or edit reverted" },
  { cls: "denied", label: "You denied a tool call" },
  { cls: "warn", label: "Changed outside the session" },
];

// the colour class of an event: matches the legend above
function tone(e: TimelineItem): string {
  switch (e.kind) {
    case "user_request": return "human";
    case "denied": return "denied";
    case "test_run": return e.exit_code === 0 ? "ok" : "bad";
    case "out_of_band": return "warn";
    case "edit": return e.reverted ? "bad" : "agent";
    default: return "agent";
  }
}

// the words for the readout under the graph
function words(e: TimelineItem): string {
  switch (e.kind) {
    case "user_request": return "You asked";
    case "denied": return "You denied a tool call";
    case "test_run": return e.exit_code === 0 ? "Tests passed" : "Tests failed";
    case "claim": return "Agent claim";
    case "out_of_band": return "Changed outside the session";
    default: return e.reverted ? "Agent edit, later reverted" : "Agent edit";
  }
}

export function TimelinePanel({ timeline, selected, onPick }: { timeline: TimelineItem[]; selected: string | null; onPick: (turn: string) => void }) {
  const n = (pred: (e: TimelineItem) => boolean) => timeline.filter(pred).length;
  const asked = n((e) => e.kind === "user_request"), edits = n((e) => e.kind === "edit");
  const tests = n((e) => e.kind === "test_run"), failed = n((e) => e.kind === "test_run" && e.exit_code !== 0);
  const summary = [plural(asked, "request"), plural(edits, "agent edit"), tests ? plural(tests, "test run") + (failed ? ` (${failed} failed)` : "") : null]
    .filter(Boolean).join(" · ");
  const nums = timeline.map((e) => tnum(e.turn));
  const lo = Math.min(...nums), hi = Math.max(...nums);
  const at = (t: string) => (hi === lo ? 50 : ((tnum(t) - lo) / (hi - lo)) * 100);
  // label only every few points when the session is long, so the numbers never collide
  const every = Math.max(1, Math.ceil(timeline.length / 12));
  const sel = timeline.find((e) => e.turn === selected);

  return (
    <Panel title="Session timeline" sub={summary}>
      <p className="tl-help">
        Each point is one step in the session, in order. Its colour says what happened there. <b>Click a point</b> to see
        the functions it touched; the decision story below then opens at them.
      </p>
      <ul className="tl-legend" aria-label="Colour key">
        {LEGEND.map((l) => <li key={l.cls}><span className={`tl-key ${l.cls}`} aria-hidden="true" />{l.label}</li>)}
      </ul>

      <div className="tl-track" role="group" aria-label="Session turns">
        <span className="tl-axis" aria-hidden="true" />
        {timeline.map((e, i) => (
          <button
            key={e.turn}
            className={`tl-dot ${tone(e)} ${selected === e.turn ? "on" : ""}`}
            style={{ left: `${at(e.turn)}%` }}
            aria-pressed={selected === e.turn}
            aria-label={`${e.turn}: ${words(e)}. ${e.label}`}
            title={`${e.turn} · ${words(e)}`}
            onClick={() => onPick(e.turn)}
          >
            {i % every === 0 && <span className="tl-num">{e.turn}</span>}
          </button>
        ))}
      </div>

      {sel ? (
        <div className="tl-read">
          <p><b className="mono">{sel.turn}</b> · {words(sel)}{sel.nodes.length ? ` · ${plural(sel.nodes.length, "function")}` : ""}</p>
          <p className="tl-label">{sel.label}</p>
          <button className="tl-go" onClick={() => document.getElementById("decision-story")?.scrollIntoView({ behavior: "smooth", block: "start" })}>
            See these functions below ↓
          </button>
        </div>
      ) : (
        <p className="tl-read tl-idle">Nothing selected. Click a point, or a function in the graph, to see its turn here.</p>
      )}
    </Panel>
  );
}

// ---- Decision story: who decided each changed function, and why. The graph shows where the code changed;
// this shows the decision behind each change.

export function DecisionStory({ files, rowsOf, sel, hot, lane, onLane, onPick }: {
  files: string[];
  rowsOf: (file: string) => { id: string; name: string; driver: Driver; change?: string; untested: boolean; reason: string | null; turns: string[] }[];
  sel: string | null; hot: Set<string>; lane: "all" | Driver | "untested"; onLane: (l: "all" | Driver | "untested") => void; onPick: (id: string) => void;
}) {
  return (
    <div id="decision-story">
      <Panel title="Decision story" sub="who decided each changed function, and why" aside={
        <Seg value={lane} onChange={onLane} options={[
          { id: "all", label: "All" }, { id: "user_asked", label: "You asked" }, { id: "agent_decided", label: "Agent" },
          { id: "not_stated", label: "No reason" }, { id: "untested", label: "Untested" }]} />}>
        <div className="ds-scroll">
          {files.length === 0 && <p className="rv-empty">Nothing matches this filter.</p>}
          {files.map((f) => (
            <div key={f} className="ds-file">
              <p className="ds-path">{f}</p>
              <ul className="ds-list">
                {rowsOf(f).map((r) => (
                  <li key={r.id}>
                    <button className={`ds-row ${sel === r.id ? "sel" : ""} ${hot.has(r.id) ? "hot" : ""}`} aria-pressed={sel === r.id} onClick={() => onPick(r.id)}>
                      <span className="ds-name">{r.name}</span>
                      <span className="ds-meta">
                        <span className={`ds-who ${r.driver === "user_asked" ? "human" : "agent"}`}>{r.driver === "user_asked" ? <User size={12} /> : <Bot size={12} />} {DRIVER[r.driver]}</span>
                        {r.change && <> · {r.change}</>}
                        {r.untested && <> · <span className="bad">untested</span></>}
                        {r.driver === "not_stated" && <> · <span className="warn">no reason</span></>}
                        {r.turns.length > 0 && <> · <span className="ds-turns">{r.turns.join(" ")}</span></>}
                      </span>
                      {r.reason && <span className="ds-why">{r.reason}</span>}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
