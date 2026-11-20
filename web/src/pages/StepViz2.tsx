import type { CSSProperties } from "react";

/* Mini visuals for the governance home (left column, one per story step). They play while their step is
   active (viz2.css); the default styles are the finished state, so reduced motion just shows the result. */

const d = (i: number): CSSProperties => ({ ["--i" as string]: i });

function Record() {
  const rows: [string, "agent" | "human", string, string][] = [
    ["T14", "agent", "wrap send() so errors are retried", "Architecture"],
    ["T16", "agent", "tenacity gives us backoff for free", "Dependency"],
    ["T18", "human", "Don't add a library for this", "Dependency · redirect"],
    ["T22", "agent", "Retrying five times, exponential", "Retries"],
  ];
  return (
    <div className="hx-vz hx-rec" aria-hidden="true">
      <i className="hx-scan" />
      {rows.map(([t, who, text, tag], k) => (
        <div key={t} className={`hx-line ${who}`} style={d(k)}>
          <b>{t}</b><span className="hx-who">{who === "agent" ? "agent" : "you"}</span>
          <span className="hx-text">{text}</span><em className="hx-tag">{tag}</em>
        </div>
      ))}
    </div>
  );
}

function Overrule() {
  return (
    <div className="hx-vz hx-diff" aria-hidden="true">
      <div className="hx-dl del" style={d(0)}><span>−</span><code>pip install tenacity</code><em>agent · T16</em></div>
      <div className="hx-dl add" style={d(1)}><span>+</span><code>delay = min(2 ** attempt, 30)</code><em>you · T18</em></div>
      <p className="hx-quote" style={d(2)}>“Don't add a library for this. Write the backoff with what we already have.”</p>
    </div>
  );
}

function Check() {
  const rules: [string, boolean, string][] = [
    ["No new runtime dependency", false, "T16"],
    ["Retries: exponential, at most 5", true, "T22"],
    ["Never skip a failing test", false, "T31"],
  ];
  return (
    <div className="hx-vz hx-chk" aria-hidden="true">
      <div className="hx-split"><i className="a" style={{ ["--w" as string]: "67%" }}>agent 6</i><i className="h" style={{ ["--w" as string]: "33%" }}>you 3</i></div>
      {rules.map(([t, ok, ref], k) => (
        <div key={t} className="hx-row" style={d(k)}>
          <span className={`hx-tick ${ok ? "ok" : "bad"}`}>{ok ? "✓" : "✕"}</span><span>{t}</span><b>{ref}</b>
        </div>
      ))}
      <div className="hx-row claim" style={d(3)}>
        <span className="hx-tick bad">✕</span><span>“Full test coverage” → <strong>unsupported</strong></span><b>T47</b>
      </div>
      <div className="hx-sum">skill adherence <b>2 of 5</b></div>
    </div>
  );
}

function Repeat() {
  const ys = [58, 30, 64, 38, 70, 24, 52, 34, 62, 28, 48];
  return (
    <div className="hx-vz hx-rep" aria-hidden="true">
      <div className="hx-axis">
        {ys.map((y, k) => <i key={k} style={{ ["--i" as string]: k, ["--x" as string]: `${4 + k * 8.6}%`, ["--y" as string]: `${y}%` }} />)}
        <span className="hx-flag">candidate</span>
      </div>
      <div className="hx-weeks">{["W1", "W2", "W3", "W4", "W5"].map((w) => <span key={w}>{w}</span>)}</div>
      <div className="hx-meta"><b className="hx-count" style={{ ["--n" as string]: 11 }} /> sessions <span>3 teams · 7 devs</span><span>rule: ≥3 sessions, ≥2 devs</span></div>
    </div>
  );
}

function Seg({ label, opts, from, to, i }: { label: string; opts: string[]; from: number; to: number; i: number }) {
  return (
    <div className="hx-ctl" style={d(i)}>
      <span className="hx-lab">{label}</span>
      <div className="hx-seg" style={{ ["--from" as string]: from, ["--to" as string]: to }}>
        <i className="hx-pill" />
        {opts.map((o, k) => <span key={o} className={k === to ? "on" : ""}>{o}</span>)}
      </div>
    </div>
  );
}

function Approve() {
  return (
    <div className="hx-vz hx-appr" aria-hidden="true">
      <p className="hx-stmt">Add no new runtime dependency without approval.</p>
      <Seg label="scope" opts={["repo", "team", "org"]} from={0} to={2} i={0} />
      <Seg label="enforcement" opts={["advice", "PR check", "gate"]} from={0} to={1} i={1} />
      <div className="hx-ctl" style={d(2)}><span className="hx-lab">expires</span><span className="hx-date">2027-03</span></div>
      <div className="hx-act"><span className="hx-btnx">Approve</span><code className="hx-out">AGENTS.md · +1 rule · PR check added</code></div>
    </div>
  );
}

function Measure() {
  return (
    <div className="hx-vz hx-loop" aria-hidden="true">
      <svg viewBox="0 0 300 110">
        <line x1="150" y1="6" x2="150" y2="104" className="hx-mark" />
        <path d="M6 18 L40 22 L80 16 L120 24 L150 30 L180 62 L215 78 L250 88 L294 94" className="hx-curve" pathLength="1" />
        <circle cx="294" cy="94" r="4" className="hx-end" />
      </svg>
      <span className="hx-pub">P-12 published</span>
      <div className="hx-nums"><span>11</span><i>→</i><span className="after">3</span> <small>overrides per 100 sessions</small></div>
    </div>
  );
}

const MAP = [null, Record, Overrule, Check, Repeat, Approve, Measure];

export default function StepViz2({ i }: { i: number }) {
  const V = MAP[i];
  return V ? <V /> : null;
}
