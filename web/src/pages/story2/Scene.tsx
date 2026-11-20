import type { CSSProperties } from "react";

/* "The new hire": one scene, two modes.
   loop: a 14 s story (corrections pile up, the senior leaves, the new hire's agent already knows).
   step: the same objects, posed per scroll step 1..5.
   Default styles are the finished frame, so reduced motion shows: senior gone, rules on the shelf, new hire fine. */

const RULES = ["no new library", "cap retries at 5", "never skip a failing test"];
const i = (n: number): CSSProperties => ({ ["--i" as string]: n });

function Person({ tone }: { tone: "senior" | "hire" }) {
  return (
    <svg className={`s2-person ${tone}`} viewBox="0 0 24 34" width="24" height="34" aria-hidden="true">
      <circle cx="12" cy="8" r="5.5" />
      <path d="M2.5 34 C2.5 19 21.5 19 21.5 34 Z" />
    </svg>
  );
}

function Bulb() {
  return (
    <svg className="s2-bulb" viewBox="0 0 20 26" width="20" height="26" aria-hidden="true">
      <path d="M10 1.5a7.5 7.5 0 0 0-4.2 13.7c.7.6 1.2 1.4 1.2 2.3v.5h6v-.5c0-.9.5-1.7 1.2-2.3A7.5 7.5 0 0 0 10 1.5Z" />
      <path d="M7.5 21.5h5M8.5 24.5h3" />
    </svg>
  );
}

export default function Scene({ mode, step = 0 }: { mode: "loop" | "step"; step?: number }) {
  return (
    <div className="s2-scene" data-mode={mode} data-step={step} role="img" aria-label="A senior developer corrects agents for months, then leaves. The corrections stay on a shelf, and the new hire's agent follows them.">
      <div className="s2-inner">
        <div className="s2-months" aria-hidden="true">
          {["JAN", "FEB", "MAR", "APR"].map((m) => <span key={m}>{m}</span>)}
          <i className="s2-mark" />
        </div>

        <div className="s2-desk">
          <div className="s2-bubs">
            {RULES.map((r, k) => <span key={r} className={`s2-bub b${k + 1}`} style={i(k)}>{r}</span>)}
          </div>
          <span className="s2-cloud" />
          <Bulb />
          <div className="s2-seat">
            <div className="s2-senior"><Person tone="senior" /></div>
            <span className="s2-chair" />
            <span className="s2-role">Senior dev</span>
          </div>
          <span className="s2-door" aria-hidden="true"><i /></span>
        </div>

        <div className="s2-right">
          <div className="s2-shelf">
            <span className="s2-shelflabel">Team rules · recorded by Unpack</span>
            {RULES.map((r, k) => <div key={r} className={`s2-card c${k + 1}`} style={i(k)}><b />{r}</div>)}
          </div>
          <div className="s2-hirezone">
            <div className="s2-agent">
              <span className="s2-tag">agent</span>
              <span className="s2-say">Following: cap retries at 5</span>
            </div>
            <div className="s2-hire">
              <span className="s2-sweat" />
              <span className="s2-check">✓</span>
              <Person tone="hire" />
              <span className="s2-role">New hire</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
