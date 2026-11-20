import Person from "./Person";

// The pinned figure of the story: three seats on top, one panel below that changes with the step.
const SEATS = [{ k: "dev", role: "Developer" }, { k: "lead", role: "Tech lead" }, { k: "cto", role: "CTO" }];
const ON: (string | null)[][] = [["dev", "lead", "cto"], ["dev"], ["lead"], ["cto"], []];

function Record() {
  const rows: [string, string, boolean, boolean][] = [
    ["T16", "agent · Add tenacity", false, true],
    ["T18", "you · No new library", true, false],
    ["T22", "agent · Exponential, 5 tries", false, false],
    ["T31", "agent · Skip flaky test", false, true],
    ["T33", "you · Don't skip, fix it", true, false],
  ];
  return (
    <div className="s4-panel">
      <h4>One record <small>every decision, pinned to a turn</small></h4>
      {rows.map(([t, x, h, struck], i) => (
        <p key={t} className={`s4-row ${h ? "human" : ""} ${struck ? "struck" : ""}`} style={{ ["--i" as string]: i }}><b>{t}</b>{x}</p>
      ))}
    </div>
  );
}

function Dev() {
  const days: [string, string][] = [["Mon", "Payments"], ["Tue", "Search"], ["Thu", "Identity"]];
  return (
    <div className="s4-panel">
      <h4>Same correction, three days <small>told 11×</small></h4>
      {days.map(([d, t], i) => (
        <p key={d} className="s4-row human" style={{ ["--i" as string]: i }}><b>{d}</b>{t} · “no new library”<em className="s4-sigh">…</em></p>
      ))}
      <p className="s4-row s4-rule" style={{ ["--i" as string]: 3 }}><b>+</b>No new runtime dependency without approval.<em>AGENTS.md</em></p>
      <p className="s4-foot">Now you say it once.</p>
    </div>
  );
}

function Lead() {
  return (
    <div className="s4-panel">
      <h4>Do agents follow our rules?</h4>
      <div className="s4-ringrow s4-big"><i className="s4-ring" style={{ ["--p" as string]: 86 }}><b>86%</b></i>
        <ul>
          <li className="bad">✕ No new runtime dependency</li>
          <li className="ok">✓ Retries: exponential, ≤ 5</li>
          <li className="bad">✕ Never skip a failing test</li>
        </ul>
      </div>
      <p className="s4-foot"><span className="s4-btn">Approve</span> candidate · 11 sessions · scope org</p>
    </div>
  );
}

function Cto() {
  return (
    <div className="s4-panel">
      <h4>Can we trust agents with more? <small>associated with the policy</small></h4>
      <svg viewBox="0 0 220 70" className="s4-chart" aria-hidden="true">
        <line x1="110" y1="2" x2="110" y2="66" className="s4-mark" />
        <path d="M4 12 L50 15 L100 11 L110 20 L150 46 L190 56 L216 60" pathLength="1" />
      </svg>
      <p className="s4-foot">Repeat overrides per 100 sessions <b>11 → 3</b> after P-12</p>
      <div className="s4-ladder"><span>advice</span><span>PR check</span><span className="on">gate relaxed</span></div>
    </div>
  );
}

function Never() {
  const rows: [string, number][] = [["by agent", 78], ["by area", 54], ["by code", 36]];
  return (
    <div className="s4-panel">
      <h4>What gets measured</h4>
      {rows.map(([l, w], i) => (
        <div key={l} className="s4-bar" style={{ ["--i" as string]: i }}><span>{l}</span><i style={{ ["--w" as string]: `${w}%` }} /></div>
      ))}
      <p className="s4-row s4-never"><b>✕</b>per-developer scores<em>never</em></p>
      <p className="s4-foot">Agents, areas and code. Never people.</p>
    </div>
  );
}

const PANELS = [Record, Dev, Lead, Cto, Never];

export default function Figure({ step }: { step: number }) {
  const P = PANELS[step];
  return (
    <div className="s4-fig">
      <div className="s4-figseats">
        {SEATS.map((s) => (
          <span key={s.k} className="s4-chip" data-on={ON[step].includes(s.k)}><Person size={18} />{s.role}</span>
        ))}
      </div>
      <P key={step} />
    </div>
  );
}
