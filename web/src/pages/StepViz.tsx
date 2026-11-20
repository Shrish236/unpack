import type { CSSProperties } from "react";

/* One small animated visual per story step, shown under the step's text.
   Each one is the idea of its step, not decoration. They play when the step becomes active (see viz.css).
   Default styles are the finished state, so with reduced motion everything is simply visible. */

const d = (i: number): CSSProperties => ({ ["--i" as string]: i });

function Session() {
  const rows: [string, "agent" | "human", string, string][] = [
    ["T14", "agent", "wrap send() so errors are retried", "Architecture"],
    ["T16", "agent", "tenacity gives us backoff for free", "Dependency"],
    ["T18", "human", "Don't add a library for this", "Dependency · redirect"],
    ["T22", "agent", "Retrying five times, exponential", "Retries"],
  ];
  return (
    <div className="vz vz-session" aria-hidden="true">
      <i className="vz-scan" />
      {rows.map(([t, who, text, tag], k) => (
        <div key={t} className={`vz-line ${who}`} style={d(k)}>
          <b className="mono">{t}</b>
          <span className="vz-who">{who === "agent" ? "agent" : "you"}</span>
          <span className="vz-text">{text}</span>
          <em className="vz-tag">{tag}</em>
        </div>
      ))}
    </div>
  );
}

function Who() {
  const rules: [string, boolean, string][] = [
    ["No new runtime dependency", false, "T16"],
    ["Retries: exponential, at most 5", true, "T22"],
    ["Never skip a failing test", false, "T31"],
  ];
  return (
    <div className="vz vz-who-card" aria-hidden="true">
      <div className="vz-split"><i className="a" style={{ ["--w" as string]: "67%" }}>agent 6</i><i className="h" style={{ ["--w" as string]: "33%" }}>you 3</i></div>
      {rules.map(([t, ok, ref], k) => (
        <div key={t} className="vz-rule" style={d(k)}>
          <span className={`vz-tick ${ok ? "ok" : "bad"}`}>{ok ? "✓" : "✕"}</span>
          <span>{t}</span><b className="mono">{ref}</b>
        </div>
      ))}
      <div className="vz-foot mono">skill adherence <b>2 of 5</b></div>
    </div>
  );
}

function Overrule() {
  return (
    <div className="vz vz-diff" aria-hidden="true">
      <div className="vz-dl del" style={d(0)}><span className="vz-sign">−</span><code>pip install tenacity</code><em>agent · T16</em></div>
      <div className="vz-dl add" style={d(1)}><span className="vz-sign">+</span><code>delay = min(2 ** attempt, 30)</code><em>you · T18</em></div>
      <p className="vz-quote" style={d(2)}>“Don't add a library for this. Write the backoff with what we already have.”</p>
    </div>
  );
}

function Iterations() {
  return (
    <div className="vz vz-flow" aria-hidden="true">
      <div className="vz-q mono">needed a second try?</div>
      <div className="vz-branches">
        <div className="vz-br yes">
          <span className="vz-ask mono">in the brief?</span>
          <b>yes</b><i>Agent missed it</i><small>AC2 · No new dependencies</small>
        </div>
        <div className="vz-br no">
          <span className="vz-ask mono">in the brief?</span>
          <b>no</b><i>Requirement was thin</i><small>AC4 · Async behaves the same</small>
        </div>
      </div>
    </div>
  );
}

function Claim() {
  const checks: [string, boolean, string][] = [
    ["Tests ran after the last edit?", false, "stale since T38"],
    ["A test reaches AsyncClient._send?", false, "none · static estimate"],
    ["The change is in the diff?", true, "yes"],
  ];
  return (
    <div className="vz vz-claim" aria-hidden="true">
      <p className="vz-quote" style={d(0)}><span className="mono">agent · T47</span> “Full test coverage.”</p>
      {checks.map(([t, ok, r], k) => (
        <div key={t} className="vz-check" style={d(k + 1)}>
          <i className="vz-spin" /><span className={`vz-tick ${ok ? "ok" : "bad"}`}>{ok ? "✓" : "✕"}</span>
          <span>{t}</span><b className="mono">{r}</b>
        </div>
      ))}
      <div className="vz-stamp mono">unsupported</div>
    </div>
  );
}

function Pattern() {
  const weeks = ["W1", "W2", "W3", "W4", "W5"];
  return (
    <div className="vz vz-pattern" aria-hidden="true">
      <div className="vz-axis">
        {Array.from({ length: 11 }, (_, k) => (
          <i key={k} className={k >= 2 ? "late" : ""} style={{ ["--i" as string]: k, ["--x" as string]: `${4 + k * 8.6}%`, ["--y" as string]: `${[58, 30, 64, 38, 70, 24, 52, 34, 62, 28, 48][k]}%` }} />
        ))}
        <span className="vz-flag mono">candidate</span>
      </div>
      <div className="vz-weeks mono">{weeks.map((w) => <span key={w}>{w}</span>)}</div>
      <div className="vz-meta mono"><b style={{ ["--n" as string]: 11 }} className="vz-count" /> sessions <span>3 teams · 7 devs</span><span>rule: ≥3 sessions, ≥2 devs</span></div>
    </div>
  );
}

function Loop() {
  return (
    <div className="vz vz-loop" aria-hidden="true">
      <svg viewBox="0 0 300 110">
        <line x1="150" y1="6" x2="150" y2="104" className="vz-mark" />
        <path d="M6 18 L40 22 L80 16 L120 24 L150 30 L180 62 L215 78 L250 88 L294 94" className="vz-curve" pathLength="1" />
        <circle cx="294" cy="94" r="4" className="vz-end" />
      </svg>
      <span className="vz-pub mono">P-12 published</span>
      <div className="vz-nums mono"><span>11</span><i>→</i><span className="after">3</span> <small>overrides per 100 sessions</small></div>
    </div>
  );
}

const MAP = [null, Session, Who, Overrule, Iterations, Claim, Pattern, Loop];

export default function StepViz({ i }: { i: number }) {
  const V = MAP[i];
  return V ? <V /> : null;
}
