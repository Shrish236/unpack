import { useEffect, useState } from "react";
import { Check, Hand } from "lucide-react";

/* Hero scene for #/home-b: "Monday to Monday".
   Three teams make the same correction in one week; Unpack folds it into one policy; next Monday the agent
   follows it unprompted. A phase counter drives CSS transitions (8 phases x 1.75 s = a 14 s loop).
   Reduced motion: the last phase, held. */

const PHASES = 8;
const SESSIONS = [
  { team: "Payments", day: "Mon", agent: "pip install tenacity" },
  { team: "Search", day: "Tue", agent: "pip install backoff" },
  { team: "Identity", day: "Thu", agent: "pip install retrying" },
];
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "next Mon"];
const DAY_AT = [0, 0, 1, 3, 3, 4, 5, 5]; // which day is lit in each phase

// a very small neutral person: head and shoulders, nothing else
function Person({ talking = false, done = false }: { talking?: boolean; done?: boolean }) {
  return (
    <span className="hb-person" aria-hidden="true">
      <svg viewBox="0 0 16 20" width="16" height="20">
        <circle cx="8" cy="5" r="3.6" />
        <path d="M1.5 19.5 C1.5 13 4 10.5 8 10.5 C12 10.5 14.5 13 14.5 19.5 Z" />
      </svg>
      {talking && <i className="hb-typing"><b /><b /><b /></i>}
      {done && <i className="hb-done"><Check size={9} strokeWidth={3} /></i>}
    </span>
  );
}

export default function SceneB() {
  const [phase, setPhase] = useState(PHASES - 1);

  useEffect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    setPhase(0);
    const t = setInterval(() => setPhase((p) => (p + 1) % PHASES), 1750);
    return () => clearInterval(t);
  }, []);

  const corrections = phase >= 6 ? 0 : Math.max(0, Math.min(3, phase - 1));
  const merged = phase >= 5;

  return (
    <div className="hb-scene" data-phase={phase} role="img"
      aria-label="Three teams make the same correction to their agents in one week. Unpack turns it into policy P-12. The next Monday the agent follows the rule without being told.">
      <div className="hb-week">
        {DAYS.map((d, k) => <span key={d} className={DAY_AT[phase] === k ? "on" : ""}>{d}</span>)}
      </div>

      {SESSIONS.map((s, k) => {
        const shown = phase >= k + 1, corrected = phase >= k + 2;
        return (
          <div key={s.team} className={`hb-row ${shown ? "in" : ""} ${merged ? "dim" : ""}`}>
            <Person talking={shown && !corrected && phase === k + 1} />
            <div className="hb-term">
              <header>{s.team} · {s.day}</header>
              <code><span className="who">agent ›</span> {s.agent}</code>
              <code className={`you ${corrected ? "in" : ""}`}><span className="who">you ›</span> no new library, use what we have</code>
            </div>
            <span className={`hb-mark ${corrected ? "in" : ""} ${merged ? "fly" : ""}`} style={{ ["--dy" as string]: `${(3 - k) * 78 - 6}px` }}>
              <Hand size={14} />
            </span>
          </div>
        );
      })}

      <div className={`hb-policy ${merged ? "in" : ""}`}>
        <span className="hb-chip-p">P-12</span> No new runtime dependency
        <small>same correction · 3 teams · 1 policy</small>
      </div>

      <div className={`hb-row hb-next ${phase >= 6 ? "in" : ""}`}>
        <Person done />
        <div className="hb-term ok">
          <header>Payments · next Mon</header>
          <code><span className="who">agent ›</span> Following P-12: using the existing retry helper.</code>
        </div>
        <span className="hb-ok"><Check size={14} strokeWidth={3} /></span>
      </div>

      <div className="hb-counter">
        repeat overrides this week <b className={phase >= 6 ? "zero" : ""}>{phase >= 6 ? "3 → 0" : corrections}</b>
      </div>
    </div>
  );
}
