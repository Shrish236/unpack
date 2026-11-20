import { useEffect, useState } from "react";
import { Cup, Person, Sigh } from "./People";

/* The hero loop (~14 s) is a list of phases. A phase only flips data attributes; CSS transitions do the motion.
   The last visible phase (9) is also the reduced-motion frame. */
const MS = [600, 1400, 800, 1400, 800, 1600, 1200, 1600, 1400, 3200, 700];
const FINAL = 9;
const DAYS = ["MON", "TUE", "WED", "THU", "FRI", "NEXT MON"];
const ROWS = [
  { role: "Dev · Payments", prop: "pip install tenacity", s: 1, at: 1 },
  { role: "Dev · Search", prop: "pip install backoff", s: 1.5, at: 3 },
  { role: "Dev · Identity", prop: "pip install retrying", s: 2.1, at: 5 },
];

function usePhase() {
  const reduce = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const [p, setP] = useState(reduce ? FINAL : 0);
  useEffect(() => {
    if (reduce) return;
    let i = 0, t = 0;
    const tick = () => { i = (i + 1) % MS.length; setP(i); t = window.setTimeout(tick, MS[i]); };
    t = window.setTimeout(tick, MS[0]);
    return () => clearTimeout(t);
  }, [reduce]);
  return p;
}

export default function HeroScene() {
  const p = usePhase();
  const day = p >= 9 ? 5 : p >= 6 ? 4 : p >= 4 ? 3 : p >= 2 ? 1 : 0;
  const live = p < 10;
  return (
    <div className="s1-scene" role="img" aria-label="Three teams give the same correction on three days. A lead approves it once. The next Monday the agent already knows.">
      <div className="s1-cal">
        <i style={{ transform: `translateX(${day * 100}%)` }} />
        {DAYS.map((d, k) => <span key={d} className={k === day ? "on" : ""}>{d}</span>)}
      </div>

      <div className="s1-rows" data-swept={p >= 6}>
        {ROWS.map((r) => (
          <div key={r.role} className="s1-row" data-show={live && p >= r.at}>
            <div className="s1-who"><Sigh s={r.s} show={p === r.at} /><Person /><span>{r.role}</span></div>
            <div className="s1-say">
              <code>agent › {r.prop}</code>
              <span className="s1-bubble">no new library</span>
            </div>
          </div>
        ))}
      </div>

      <div className="s1-card" data-show={live && p >= 6}>
        <div className="s1-card-h"><b>seen 3×</b><span>3 teams</span><em data-show={p >= 8 && live}>P-12 · policy</em></div>
        <p>No new runtime dependency.</p>
        <div className="s1-lead" data-show={live && p >= 7}>
          <Person kind="lead" /><span>Tech lead</span>
          <button type="button" tabIndex={-1} className="s1-approve" data-state={p >= 8 ? "done" : p === 7 ? "tap" : "idle"}>{p >= 8 ? "Approved ✓" : "Approve"}</button>
        </div>
      </div>

      <div className="s1-row s1-last" data-show={live && p >= 9}>
        <div className="s1-who"><Person lean={p >= 9} /><Cup /><span>Dev · Payments · next Mon</span></div>
        <div className="s1-say">
          <span className="s1-agent">Got it — using the existing helper ✓</span>
          <code>repeat corrections this week <b>3 → 0</b></code>
        </div>
      </div>
    </div>
  );
}
