import { Cup, Person, Sigh } from "./People";

// One pinned mini-scene per story step. Keyed by step so the CSS "from" animations replay on every change.
const Bubble = ({ dim = false }: { dim?: boolean }) => <span className={`s1-bubble ${dim ? "dim" : ""}`}>no new library</span>;
const Dev = ({ role, s, dim }: { role: string; s: number; dim?: boolean }) => (
  <div className={`s1-dev ${dim ? "dim" : ""}`}><Sigh s={s} /><Person /><span>{role}</span></div>
);

export default function StoryScene({ step }: { step: number }) {
  return (
    <div className="s1-st" key={step} aria-hidden="true">
      <div className="s1-st-h mono">{["MONDAY", "TUESDAY", "THURSDAY", "FRIDAY", "NEXT MONDAY"][step]}</div>

      {step === 0 && (
        <>
          <div className="s1-line"><Dev role="Dev · Payments" s={1} /><Bubble /></div>
          <div className="s1-chip-card s1-rise"><b className="mono">T18 · you · redirect</b><span>“Don't add a library for this.”</span><small>recorded with who, turn and your exact words</small></div>
        </>
      )}
      {step === 1 && (
        <>
          <div className="s1-line"><Dev role="Dev · Payments" s={1} dim /><Bubble dim /></div>
          <div className="s1-line s1-rise"><Dev role="Dev · Search" s={1.5} /><Bubble /></div>
          <div className="s1-chip-card s1-rise"><b className="mono">same correction</b><span>a second team, a different agent</span></div>
        </>
      )}
      {step === 2 && (
        <>
          <div className="s1-trio">
            <Dev role="Payments" s={1} dim /><Dev role="Search" s={1.5} dim /><Dev role="Identity" s={2.1} />
          </div>
          <div className="s1-heap"><Bubble dim /><Bubble dim /><Bubble /></div>
          <div className="s1-chip-card s1-rise yellow"><b className="mono">policy candidate</b><span>3 sessions · 3 teams · 3 developers</span><small>rule: at least 3 sessions and 2 developers</small></div>
        </>
      )}
      {step === 3 && (
        <div className="s1-chip-card s1-rise s1-form">
          <div className="s1-lead2"><Person kind="lead" /><span>Tech lead</span></div>
          <p>No new runtime dependency.</p>
          <div className="s1-seg"><i>repo</i><i>team</i><i className="on">org</i></div>
          <div className="s1-seg"><i>advice</i><i className="on">PR check</i><i>gate</i></div>
          <div className="s1-seg"><i className="on">expires 2027-03</i><i>owner @platform</i></div>
          <button type="button" tabIndex={-1} className="s1-approve" data-state="tap">Approve</button>
        </div>
      )}
      {step === 4 && (
        <>
          <div className="s1-line"><div className="s1-dev"><Person lean /><Cup /><span>Dev · Payments</span></div><span className="s1-agent s1-rise">Got it — using the existing helper ✓</span></div>
          <div className="s1-chip-card s1-rise"><b className="mono">AGENTS.md</b><code>+ No new runtime dependency without approval.</code></div>
          <div className="s1-count s1-rise mono">repeat corrections this week <b>3 → 0</b></div>
        </>
      )}
    </div>
  );
}
