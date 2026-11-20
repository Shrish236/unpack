import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import "../../styles/homea.css";

/* Scene A: one correction, followed through real product surfaces.
   Six surfaces on one board; each story step focuses one (the others dim). Step 0 cycles the whole journey.
   Default styles are the finished state; animations only run on the focused surface, so they replay on every change. */

const d = (i: number): CSSProperties => ({ ["--i" as string]: i });

/** A tiny neutral person: head and body, no face. `tone` picks the colour (yours = accent). */
function Person({ tone = "other", title }: { tone?: "you" | "other" | "lead"; title?: string }) {
  return (
    <svg className={`ha-person ${tone}`} viewBox="0 0 16 20" width="14" height="18" role={title ? "img" : undefined} aria-label={title} aria-hidden={title ? undefined : true}>
      <circle cx="8" cy="5" r="4" />
      <path d="M1.5 20v-3.5a6.5 6.5 0 0 1 13 0V20z" />
    </svg>
  );
}

function Session() {
  return (
    <section className="ha-surface ha-s1" data-n="1">
      <header className="ha-bar"><i /><i /><i /><span>payments-api · agent session</span></header>
      <div className="ha-chat">
        <div className="ha-msg agent"><b>agent · T16</b>Adding tenacity for backoff and jitter.<code>+ tenacity = "^8.2"</code></div>
        <div className="ha-msg you"><b>you · T18</b><span className="ha-typed">Don't add a library for this. Use what we have.</span></div>
        <div className="ha-who"><Person tone="you" title="You" /><span className="ha-dots"><i /><i /><i /></span></div>
      </div>
    </section>
  );
}

function Record() {
  return (
    <section className="ha-surface ha-s2" data-n="2">
      <header className="ha-head"><span>Decision record</span><em>Dependency</em></header>
      <div className="ha-row agent"><span className="ha-x">✕</span><div><s>Add tenacity</s><small>agent · T16</small></div></div>
      <div className="ha-row you"><span className="ha-v">✓</span><div><b>Use stdlib backoff</b><small>you · redirect · T18</small></div></div>
      <q className="ha-q">Don't add a library for this.</q>
    </section>
  );
}

function Check() {
  const rules: [string, boolean][] = [["No new runtime dependency", false], ["Exponential, at most 5", true], ["Never skip a failing test", false]];
  return (
    <section className="ha-surface ha-s3" data-n="3">
      <header className="ha-head"><span>Skill check</span><em>2 of 5 followed</em></header>
      {rules.map(([t, ok], k) => (
        <div key={t} className="ha-rule" style={d(k)}><span className={ok ? "ha-v" : "ha-x"}>{ok ? "✓" : "✕"}</span>{t}</div>
      ))}
      <div className="ha-claim" style={d(3)}>“Full test coverage” <b>unsupported</b></div>
    </section>
  );
}

function Stack() {
  const teams = ["Payments", "Search", "Identity"];
  return (
    <section className="ha-surface ha-s4" data-n="4">
      <header className="ha-head"><span>Same correction</span><em className="ha-cand">Policy candidate</em></header>
      <div className="ha-copies">
        {teams.map((t, k) => (
          <div key={t} className="ha-copy" style={d(k)}><Person tone={k === 0 ? "you" : "other"} /><span>{t}</span><small>no new library</small></div>
        ))}
      </div>
      <div className="ha-count"><b className="ha-n" style={{ ["--ha-n" as string]: 11 }} /> sessions · 3 teams · 7 devs</div>
    </section>
  );
}

function Inbox() {
  return (
    <section className="ha-surface ha-s5" data-n="5">
      <header className="ha-head"><span>Governance inbox</span><em>P-12</em></header>
      <p className="ha-stmt">Add no new runtime dependency without approval.</p>
      <dl className="ha-form"><dt>Scope</dt><dd>org</dd><dt>Enforce</dt><dd>PR check</dd><dt>Expires</dt><dd>2027-03</dd></dl>
      <div className="ha-act">
        <Person tone="lead" title="Reviewer" />
        <span className="ha-btn"><span className="a">Approve</span><span className="b">Approved ✓</span></span>
        <svg className="ha-cursor" viewBox="0 0 12 16" width="12" height="16" aria-hidden="true"><path d="M1 1v12l3.2-3 2.3 5 2-1-2.2-4.9H11z" /></svg>
      </div>
    </section>
  );
}

function Publish() {
  return (
    <section className="ha-surface ha-s6" data-n="6">
      <header className="ha-head"><span className="ha-file">AGENTS.md</span><em>+1 rule</em></header>
      <div className="ha-md"><span className="ha-add">+ Add no new runtime dependency without approval.</span></div>
      <div className="ha-msg agent ha-next"><b>agent · next session</b>Following P-12: using the existing retry helper.</div>
      <div className="ha-drop">overrides this week <b>3</b> → <b className="ok">0</b></div>
    </section>
  );
}

/** Connector paths between consecutive surfaces, measured from the laid-out cards:
    side by side -> right edge to left edge; next row -> bottom centre, elbow, top centre. */
function useLinks(board: React.RefObject<HTMLDivElement | null>) {
  const [links, setLinks] = useState<{ w: number; h: number; d: string[] }>({ w: 1, h: 1, d: [] });
  useLayoutEffect(() => {
    const el = board.current;
    if (!el) return;
    const measure = () => {
      const b = el.getBoundingClientRect();
      const r = [1, 2, 3, 4, 5, 6].map((n) => el.querySelector(`.ha-s${n}`)!.getBoundingClientRect());
      const d = r.slice(1).map((to, k) => {
        const a = r[k];
        if (to.left >= a.right - 2) { // next card sits to the right
          const y = (Math.max(a.top, to.top) + Math.min(a.bottom, to.bottom)) / 2 - b.top;
          return `M${a.right - b.left} ${y} H${to.left - b.left}`;
        }
        const x1 = a.left + a.width / 2 - b.left, y1 = a.bottom - b.top, x2 = to.left + to.width / 2 - b.left, y2 = to.top - b.top;
        const mid = (y1 + y2) / 2;
        return `M${x1} ${y1} V${mid} H${x2} V${y2}`;
      });
      setLinks({ w: b.width, h: b.height, d });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [board]);
  return links;
}

export default function SceneA({ step }: { step: number }) {
  const still = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const [demo, setDemo] = useState(1);
  // step 0 is the hero: walk the whole journey in a loop
  useEffect(() => {
    if (step !== 0 || still) return;
    setDemo(1);
    const t = setInterval(() => setDemo((n) => (n % 6) + 1), 2000);
    return () => clearInterval(t);
  }, [step, still]);
  const focus = step === 0 ? (still ? 0 : demo) : step;
  const board = useRef<HTMLDivElement>(null);
  const links = useLinks(board);

  return (
    <div ref={board} className="ha-board" data-f={focus} aria-label="One correction followed from the agent session to the rule every agent reads">
      <svg className="ha-links" viewBox={`0 0 ${links.w} ${links.h}`} aria-hidden="true">
        {links.d.map((p, k) => <path key={k} d={p} className={focus === k + 2 ? "on" : focus > k + 2 ? "done" : ""} />)}
      </svg>
      <Session /><Record /><Check /><Stack /><Inbox /><Publish />
      <span className="ha-ghost" aria-hidden="true">Don't add a library for this.</span>
    </div>
  );
}
