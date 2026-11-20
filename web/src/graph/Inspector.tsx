// The reasoning panel. It opens on selection and is never empty: with nothing selected it shows the summary.
import { AlertTriangle, Bot, FlaskConical, HelpCircle, User } from "lucide-react";
import type { AnalysisResponse, GNode } from "../api";
import {
  CHANGE_STYLE, CHANGE_WORDS, DRIVER_WORDS, SOURCE_WORDS, TEST_WORDS, changeKindOf, cardKind, isUntested,
  lastName, type ChangeKind, type Graph,
} from "./model";

const DRIVER_ICON = { user_asked: User, agent_decided: Bot, not_stated: HelpCircle } as const;

function Summary({ g, order, onSelect }: { g: Graph; order?: string[]; onSelect: (id: string) => void }) {
  const list = (order ?? g.changed.map((n) => n.id)).map((id) => g.byId[id]).filter(Boolean);
  const a: AnalysisResponse = g.analysis;
  const kinds = (Object.keys(g.counts) as ChangeKind[]).filter((k) => g.counts[k] > 0);
  return (
    <div className="gl-insp-body">
      <h3 className="gl-insp-title">This change</h3>
      <p className="gl-muted">Select a dot or card to see why it changed, who asked for it, and which tests reach it.</p>
      <ul className="gl-kv">
        <li><b>{g.changed.length}</b> functions changed</li>
        {kinds.map((k) => <li key={k}><span className="gl-sw" style={{ background: CHANGE_STYLE[k].color }} /><b>{g.counts[k]}</b> {CHANGE_STYLE[k].label.toLowerCase()}</li>)}
        <li><b className={g.untested ? "gl-bad" : ""}>{g.untested}</b> with no test reaching them</li>
        <li><b>{g.outsideSession}</b> changed outside the session</li>
      </ul>
      <h4 className="gl-sec-h">Reading order</h4>
      <ol className="gl-order">
        {list.slice(0, 8).map((n) => (
          <li key={n.id}>
            <button className="gl-link" onClick={() => onSelect(n.id)}>{n.label}</button>
            <span className="gl-muted mono"> {n.path.split("/").pop()}</span>
          </li>
        ))}
      </ol>
      {list.length > 8 && <p className="gl-muted">+{list.length - 8} more. Open a folder to see them, or use the arrow keys.</p>}
      {a.findings.length > 0 && (
        <>
          <h4 className="gl-sec-h">Findings</h4>
          <ul className="gl-findings">
            {a.findings.map((f) => (
              <li key={f.id}>
                <b>{f.finding}</b>
                {f.functions[0] && <button className="gl-link" onClick={() => onSelect(f.functions[0])}>{lastName(f.functions[0])}</button>}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function Quote({ turn, quote, who }: { turn: string; quote: string; who: "user" | "agent" }) {
  return (
    <blockquote className={`gl-quote ${who}`}>
      <small className="mono">{turn}</small>
      “{quote}”
    </blockquote>
  );
}

function NodeDetail({ g, n }: { g: Graph; n: GNode }) {
  const a = g.analysis;
  const r = a.reasons[n.id];
  const ck = changeKindOf(n) as ChangeKind | null;
  const hits = a.impact.by_node[n.id] ?? [];
  const findings = a.findings.filter((f) => f.functions.includes(n.id));
  const hunks = a.diff_hunks[n.id] ?? [];
  const kind = cardKind(n);
  const DriverIcon = r ? DRIVER_ICON[r.driver] : HelpCircle;
  const depths = [1, 2, 3].map((d) => ({ d, count: hits.filter((h) => h.depth === d && !h.uncertain).length, uncertain: hits.filter((h) => h.depth === d && h.uncertain).length }));

  return (
    <div className="gl-insp-body">
      <div className="gl-chips">
        {ck && <span className="gl-chip-badge" style={{ color: CHANGE_STYLE[ck].text }}>{CHANGE_STYLE[ck].label}</span>}
        {n.change?.source === "outside_session" && <span className="gl-chip-badge warn">outside session</span>}
        {kind === "context" && <span className="gl-chip-badge">context</span>}
        {kind === "test" && <span className="gl-chip-badge">test</span>}
        {r && <span className="gl-chip-badge"><DriverIcon size={12} /> {DRIVER_WORDS[r.driver]}</span>}
        {r && <span className="gl-chip-badge">{r.confidence} confidence</span>}
      </div>
      <h3 className="gl-insp-title">{n.label}</h3>
      <p className="gl-muted mono">{n.path}{n.start_line ? `:${n.start_line}–${n.end_line}` : ""}</p>
      {n.signature && <pre className="gl-sig">{n.signature}</pre>}

      {ck && <section className="gl-sec"><h4 className="gl-sec-h">What changed</h4><p>{CHANGE_WORDS[ck]}. {n.change && SOURCE_WORDS[n.change.source]}.</p></section>}

      <section className="gl-sec">
        <h4 className="gl-sec-h">Why</h4>
        {r ? (
          <>
            <p className="gl-reason">{r.reason ?? "No reason given in the session."}</p>
            {r.history.length > 0 && (
              <ol className="gl-history">
                {r.history.map((h) => <li key={h.turn + h.text}><span className="mono">{h.turn}</span> {h.text}</li>)}
              </ol>
            )}
            {r.evidence.map((e) => <Quote key={e.turn + e.quote} turn={e.turn} quote={e.quote} who="user" />)}
          </>
        ) : <p className="gl-muted">No reason found in the session.</p>}
      </section>

      {findings.length > 0 && (
        <section className="gl-sec">
          <h4 className="gl-sec-h">Findings</h4>
          {findings.map((f) => (
            <p key={f.id} className="gl-finding"><AlertTriangle size={13} /> {f.finding}</p>
          ))}
        </section>
      )}

      {n.test !== null && (
        <section className="gl-sec">
          <h4 className="gl-sec-h">Tests</h4>
          <p className={isUntested(n) ? "gl-bad" : ""}><FlaskConical size={13} /> {TEST_WORDS[n.test?.label ?? "none"]}{n.test && n.test.count > 0 ? ` (${n.test.count})` : ""}</p>
          {n.test?.shortest_path && n.test.shortest_path.length > 1 && (
            <p className="gl-muted mono">{n.test.shortest_path.map(lastName).join(" → ")}</p>
          )}
          {isUntested(n) && n.test?.nearest_tested && <p className="gl-muted">Nearest tested: {lastName(n.test.nearest_tested)}</p>}
        </section>
      )}

      <section className="gl-sec">
        <h4 className="gl-sec-h">Blast radius</h4>
        <p className="gl-muted">{n.callers_count} direct caller{n.callers_count === 1 ? "" : "s"} · {n.callees_count} callee{n.callees_count === 1 ? "" : "s"}</p>
        {hits.length > 0 && (
          <ul className="gl-kv small">
            {depths.map((x) => x.count + x.uncertain > 0 && (
              <li key={x.d}>{x.d} hop{x.d > 1 ? "s" : ""}: {x.count}{x.uncertain ? ` + ${x.uncertain} uncertain` : ""}</li>
            ))}
          </ul>
        )}
      </section>

      {hunks.length > 0 && (
        <section className="gl-sec">
          <h4 className="gl-sec-h">Diff</h4>
          <pre className="gl-diff">
            {hunks.flatMap((h) => h.patch.split("\n")).map((line, i) => (
              <span key={i} className={line[0] === "+" ? "add" : line[0] === "-" ? "del" : line[0] === "@" ? "hh" : ""}>{line}{"\n"}</span>
            ))}
          </pre>
        </section>
      )}

      {r?.history.length === 0 && r.evidence.length === 0 && <p className="gl-muted">Reason is recorded, but no turns quote it.</p>}
    </div>
  );
}

export default function Inspector({ g, sel, order, onSelect }: { g: Graph; sel: string | null; order?: string[]; onSelect: (id: string) => void }) {
  const n = sel ? g.byId[sel] : undefined;
  return <aside className="panel gl-insp" aria-label="Reasoning panel">{n ? <NodeDetail g={g} n={n} /> : <Summary g={g} order={order} onSelect={onSelect} />}</aside>;
}
