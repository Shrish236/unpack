import Person from "./Person";

// Hero scene: three seats, one shared record, three reliefs. A 14 s loop (see story4.css).
// Default styles are the finished frame (worries gone, reliefs shown), so reduced motion shows the payoff.
const SEATS = [
  { n: 1, role: "Developer", worry: "Stop making me repeat myself.", ok: "Said it once.", emote: "sigh" },
  { n: 2, role: "Tech lead", worry: "Are agents following our standards?", ok: "86% follow the rules.", emote: "ask" },
  { n: 3, role: "CTO", worry: "Can I trust agents with more?", ok: "Overrides 11 → 3.", emote: "sweat" },
];

export default function Scene() {
  return (
    <div className="s4-scene" role="img" aria-label="A developer, a tech lead and a CTO each worry about agents. One shared record of decisions answers all three.">
      <div className="s4-seats">
        {SEATS.map((s) => (
          <div key={s.n} className="s4-seat">
            <div className="s4-bubble">
              <span className={`s4-worry s4-w${s.n}`}>{s.worry}</span>
              <span className={`s4-okline s4-o${s.n}`}>✓ {s.ok}</span>
            </div>
            <div className="s4-who">
              <Person />
              <span className="s4-emote">
                <i className={`s4-e-w s4-e-${s.emote} s4-w${s.n}`} />
                <i className={`s4-e-ok s4-o${s.n}`}>✓</i>
              </span>
            </div>
            <b className="s4-role">{s.role}</b>
          </div>
        ))}
      </div>

      <div className="s4-ledger">
        <header><span>Shared record</span><em>one source</em></header>
        <p className="s4-l struck"><b>T16</b> agent · Add tenacity <i>overruled</i></p>
        <p className="s4-l human"><b>T18</b> you · No new library <i>redirect</i></p>
        <p className="s4-l"><b>T22</b> agent · Exponential, 5 tries</p>
        <p className="s4-l human"><b>11</b> sessions · 3 teams → candidate</p>
      </div>

      <svg className="s4-links" viewBox="0 0 300 36" preserveAspectRatio="none" aria-hidden="true">
        <path className="s4-link s4-k1" d="M150 0 C150 20 50 14 50 36" pathLength="1" />
        <path className="s4-link s4-k2" d="M150 0 L150 36" pathLength="1" />
        <path className="s4-link s4-k3" d="M150 0 C150 20 250 14 250 36" pathLength="1" />
      </svg>

      <div className="s4-results">
        <div className="s4-res s4-r1">
          <small>Developer</small>
          <code>+ No new runtime dependency</code>
          <span className="s4-tag">+1 rule in AGENTS.md</span>
        </div>
        <div className="s4-res s4-r2">
          <small>Tech lead</small>
          <div className="s4-ringrow"><i className="s4-ring" style={{ ["--p" as string]: 86 }}><b>86</b></i><span className="s4-btn">Approve</span></div>
        </div>
        <div className="s4-res s4-r3">
          <small>CTO</small>
          <svg viewBox="0 0 80 28" className="s4-mini"><path d="M2 5 L22 6 L36 8 L46 18 L62 23 L78 25" pathLength="1" /></svg>
          <span className="s4-tag">overrides 11 → 3 · gate → PR check</span>
        </div>
      </div>
    </div>
  );
}
